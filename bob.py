import asyncio
import json
from ctypes import cdll
from time import sleep
import platform

import logging

from demo_utils import file_ext
from vcx.api.connection import Connection
from vcx.api.credential import Credential
from vcx.api.disclosed_proof import DisclosedProof
from vcx.api.proof import Proof
from vcx.api.utils import vcx_agent_provision
from vcx.api.vcx_init import vcx_init_with_config
from vcx.state import State, ProofState

# logging.basicConfig(level=logging.DEBUG) uncomment to get logs

provisionConfig = {
    'agency_url': 'https://agency.pps.evernym.com',
    'agency_did': '3mbwr7i85JNSL3LoNQecaW',
    'agency_verkey': '2WXxo6y1FJvXWgZnoYUP5BJej2mceFrqBDNPE3p6HDPf',
    'wallet_name': 'bob_wallet',
    'wallet_key': '123',
    'payment_method': 'null',
    'enterprise_seed': '000000000000000000000000Trustee1'
}

async def get_medical_record():
    print("#9b Input doctor.py invitation details")
    details = input('invite details: ')

    print("#10b Convert to valid json and string and create a connection to doctor")
    jdetails = json.loads(details)
    connection_to_doctor = await Connection.create_with_details('doctor', json.dumps(jdetails))
    await connection_to_doctor.connect('{"use_public_did": true}')
    await connection_to_doctor.update_state()

    print("#11b Wait for doctor.py to issue a credential offer")
    sleep(10)
    offers = await Credential.get_offers(connection_to_doctor)

    # Create a credential object from the credential offer
    credential = await Credential.create('credential', offers[0])

    print("#15b After receiving credential offer, send credential request")
    await credential.send_request(connection_to_doctor, 0)

    print("#16b Poll agency and accept credential offer from doctor")
    credential_state = await credential.get_state()
    while credential_state != State.Accepted:
        sleep(2)
        await credential.update_state()
        credential_state = await credential.get_state()

    print("Credential issued")
    

async def connect_to_responder(config):
    print("Input responder.py invitation details")
    details = input('invite details: ')

    print("Convert to valid json and string and create a connection to responder")
    jdetails = json.loads(details)
    connection_to_responder = await Connection.create_with_details('responder', json.dumps(jdetails))
    await connection_to_responder.connect('{"use_public_did": true}')
    await connection_to_responder.update_state()
    print("Established connection to responder")

    print("Poll responder agency for a proof request")
    requests = await DisclosedProof.get_requests(connection_to_responder)
    while(len(requests) < 1):
        sleep(2)
        requests = await DisclosedProof.get_requests(connection_to_responder)

    #Bob gets the request from the responder
    print("Request found. Verifying responder identity before responding.")
    #Bob wants to verify the responder's identity before sharing personal info

    print("Verifying responder license")
    proof_attrs = [
        {'name': 'title', 'restrictions': [{'issuer_did': config['institution_did']}]},
        {'name': 'date', 'restrictions': [{'issuer_did': config['institution_did']}]},
        {'name': 'license_number', 'restrictions': [{'issuer_did': config['institution_did']}]}
    ]

    print("Create a Proof object for the responder's license")
    license_proof = await Proof.create('proof_uuid', 'proof_from_responder', proof_attrs, {})

    print("Request license from responder")
    await license_proof.request_proof(connection_to_responder)
    
    print("Poll agency and wait for responder to provide license proof")
    proof_state = await license_proof.get_state()
    while proof_state != State.Accepted:
        sleep(2)
        await license_proof.update_state()
        proof_state = await license_proof.get_state()

    print("Process the proof provided by the responder")
    await license_proof.get_proof(connection_to_responder)

    print("Check if license is valid")
    if license_proof.proof_state == ProofState.Verified:
        verified = True
    else:
        verified = False

    if(verified):
        print("Responder license verified. Sending medical information.")
        proof = await DisclosedProof.create('proof', requests[0])

        credentials = await proof.get_creds()

        # Use the first available credentials to satisfy the proof request
        for attr in credentials['attrs']:
            credentials['attrs'][attr] = {
                'credential': credentials['attrs'][attr][0]
            }

        print("Generating the proof")
        await proof.generate_proof(credentials, {})

        print("Sending the proof to responder")
        await proof.send_proof(connection_to_responder)
    else:
        print("Responder License could not be verified.")

async def main():
    payment_plugin = cdll.LoadLibrary('libnullpay' + file_ext())
    payment_plugin.nullpay_init()

    print("#7 Provision an agent and wallet, get back configuration details")
    config = await vcx_agent_provision(json.dumps(provisionConfig))
    config = json.loads(config)
    # Set some additional configuration options specific to bob
    config['institution_name'] = 'bob'
    config['institution_logo_url'] = 'http://robohash.org/736'
    config['genesis_path'] = 'genesis.txn'

    print("#8 Initialize libvcx with new configuration")
    await vcx_init_with_config(json.dumps(config))

    print("Bob goes to the doctor")
    await get_medical_record()

    print("Bob has medical record")

    print("Oh no! Bob got in an accident! A first responder is on the scene and wants a copy of Bob's medical record!")
    await connect_to_responder(config)



if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())