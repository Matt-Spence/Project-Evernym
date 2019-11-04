import asyncio
import json
import random
from ctypes import cdll
from time import sleep
import platform

import logging

from demo_utils import file_ext
from vcx.api.connection import Connection
from vcx.api.credential_def import CredentialDef
from vcx.api.issuer_credential import IssuerCredential
from vcx.api.proof import Proof
from vcx.api.schema import Schema
from vcx.api.utils import vcx_agent_provision
from vcx.api.vcx_init import vcx_init_with_config
from vcx.state import State, ProofState

# logging.basicConfig(level=logging.DEBUG) uncomment to get logs

# 'agency_url': URL of the agency
# 'agency_did':  public DID of the agency
# 'agency_verkey': public verkey of the agency
# 'wallet_name': name for newly created encrypted wallet
# 'wallet_key': encryption key for encoding wallet
# 'payment_method': method that will be used for payments
provisionConfig = {
  'agency_url':'https://eas01.pps.evernym.com',
  'agency_did':'UNM2cmvMVoWpk6r3pG5FAq',
  'agency_verkey':'FvA7e4DuD2f9kYHq6B3n7hE7NQvmpgeFRrox3ELKv9vX',
  'wallet_name':'doctor_wallet',
  'wallet_key':'123',
  'payment_method': 'null',
  'enterprise_seed':'000000000000000000000000Trustee1'
}

async def main():

    payment_plugin = cdll.LoadLibrary('libnullpay' + file_ext())
    payment_plugin.nullpay_init()

    print("#1b Provision an agent and wallet, get back configuration details")
    config = await vcx_agent_provision(json.dumps(provisionConfig))
    config = json.loads(config)
    # Set some additional configuration options specific to faber
    config['institution_name'] = 'Doctor'
    config['institution_logo_url'] = 'http://robohash.org/123'
    config['genesis_path'] = 'genesis.txn'

    print("#2b Initialize libvcx with new configuration")
    await vcx_init_with_config(json.dumps(config))

    print("#3b Create a new Schema on the ledger")
    version = format("%d.%d.%d" % (random.randint(1, 101), random.randint(1, 101), random.randint(1, 101)))
    schema = await Schema.create('schema_uuid', 'medical record schema', version, ['name', 'blood type', 'gender', 'date', 'diabetes'], 0)
    schema_id = await schema.get_schema_id()

    print("#4b Create a new credential definition on the ledger")
    cred_def = await CredentialDef.create('credef_uuid', 'medical record', schema_id, 0)
    cred_def_handle = cred_def.handle
    cred_def_id = await cred_def.get_cred_def_id()

    print("#5b Create a connection to bob and print out the invite details")
    connection_to_bob = await Connection.create('bob')
    await connection_to_bob.connect('{"use_public_did": true}')
    await connection_to_bob.update_state()
    details = await connection_to_bob.invite_details(False)
    print("**invite details**")
    print(json.dumps(details))
    print("******************")

    print("#6b Poll agency and wait for alice to accept the invitation (start alice.py now)")
    connection_state = await connection_to_bob.get_state()
    while connection_state != State.Accepted:
        sleep(2)
        await connection_to_bob.update_state()
        connection_state = await connection_to_bob.get_state()

    schema_attrs = {
        'name': 'bob',
        'blood type': 'O-positive',
        'gender': 'male',
        'date': '07-13-19',
        'diabetes':'Type 1'
    }

    print("#12b Create an IssuerCredential object using the schema and credential definition")
    credential = await IssuerCredential.create('bob_medical_record', schema_attrs, cred_def_handle, 'cred', '0')

    print("#13b Issue credential offer to bob")
    await credential.send_offer(connection_to_bob)
    await credential.update_state()

    print("#14b Poll agency and wait for bob to send a credential request")
    credential_state = await credential.get_state()
    while credential_state != State.RequestReceived:
        sleep(2)
        await credential.update_state()
        credential_state = await credential.get_state()

    print("#17b Issue credential to bob")
    await credential.send_credential(connection_to_bob)

    print("#18b Wait for bob to accept credential")
    await credential.update_state()
    credential_state = await credential.get_state()
    while credential_state != State.Accepted:
        sleep(2)
        await credential.update_state()
        credential_state = await credential.get_state()
    
    print("#19b Bob accepted credential")

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
    