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
    'wallet_name': 'responder_wallet',
    'wallet_key': '123',
    'payment_method': 'null',
    'enterprise_seed': '000000000000000000000000Trustee1'
}

async def get_license():
    print("#9a Input dshs.py invitation details")
    details = input('invite details: ')

    print("#10a Convert to valid json and string and create a connection to dshs")
    jdetails = json.loads(details)
    connection_to_dshs = await Connection.create_with_details('dshs', json.dumps(jdetails))
    await connection_to_dshs.connect('{"use_public_did": true}')
    await connection_to_dshs.update_state()

    print("#11a Wait for dshs.py to issue a credential offer")
    sleep(10)
    offers = await Credential.get_offers(connection_to_dshs)

    # Create a credential object from the credential offer
    credential = await Credential.create('credential', offers[0])

    print("#15a After receiving credential offer, send credential request")
    await credential.send_request(connection_to_dshs, 0)

    print("#16a Poll agency and accept credential offer from dshs")
    credential_state = await credential.get_state()
    while credential_state != State.Accepted:
        sleep(2)
        await credential.update_state()
        credential_state = await credential.get_state()

async def get_patient_record(config, name):
    print("Create Connection to patient and print out invite details")
    connection_to_patient = await Connection.create(name)
    await connection_to_patient.connect('{"use_public_did": true}')
    await connection_to_patient.update_state()
    details = await connection_to_patient.invite_details(False)
    print("**patient invite details**")
    print(json.dumps(details))
    print("******************")

    print("Poll agency and wait for patient to accept the invitation")
    connection_state = await connection_to_patient.get_state()
    while connection_state != State.Accepted:
        sleep(2)
        await connection_to_patient.update_state()
        connection_state = await connection_to_patient.get_state()

    print("Established Connection to patient")
    proof_attrs = [
        {'name': 'name', 'restrictions': [{'issuer_did': config['institution_did']}]},
        {'name': 'blood type', 'restrictions': [{'issuer_did': config['institution_did']}]},
        {'name': 'gender', 'restrictions': [{'issuer_did': config['institution_did']}]},
        {'name': 'date', 'restrictions': [{'issuer_did': config['institution_did']}]},
        {'name': 'diabetes', 'restrictions': [{'issuer_did': config['institution_did']}]}
    ]

    print("Create a Proof object for patient medical record")
    proof = await Proof.create('proof_uuid', 'proof_from_'+name, proof_attrs, {})

    print("Request medical record from patient")
    await proof.request_proof(connection_to_patient)
    #Responder requests medical records
    #patient responds with request for responder license
    print("Poll patient agency for proof request")
    requests = await DisclosedProof.get_requests(connection_to_patient)
    while(len(requests) < 1):
        sleep(2)
        requests = await DisclosedProof.get_requests(connection_to_patient)

    print("Responder received patient request.")
    license_proof = await DisclosedProof.create('proof', requests[0])

    print("Patient wants to verify Responder's license before releasing personal information.")
    credentials = await license_proof.get_creds()

    # Use the first available credentials to satisfy the proof request
    for attr in credentials['attrs']:
        credentials['attrs'][attr] = {
            'credential': credentials['attrs'][attr][0]
        }

    print("Generating proof")
    await license_proof.generate_proof(credentials, {})

    print("Sending proof to patient")
    await license_proof.send_proof(connection_to_patient)
    
    print("Poll patient agency and wait for patient to provide medical record")
    proof_state = await proof.get_state()
    while proof_state != State.Accepted:
        sleep(2)
        await proof.update_state()
        proof_state = await proof.get_state()

    print("Processing the proof provided by patient")
    await proof.get_proof(connection_to_patient)

    print("Checking if proof is valid")
    if proof.proof_state == ProofState.Verified:
        print("Medical Record Verified!!!")
        medical_record = json.dumps(await proof.serialize(), indent=4)
        medical_record_json = json.loads(medical_record)
        received_proof = medical_record_json["data"]["proof"]["libindy_proof"]
        received_proof_json =json.loads(received_proof)
        print("Received Proof: ")
        print(json.dumps(received_proof_json["requested_proof"], indent=2))
    else:
        print("could not verify medical record :(")

async def main():
    payment_plugin = cdll.LoadLibrary('libnullpay' + file_ext())
    payment_plugin.nullpay_init()

    print("#7a Provision an agent and wallet, get back configuration details")
    config = await vcx_agent_provision(json.dumps(provisionConfig))
    config = json.loads(config)
    # Set some additional configuration options specific to alice
    config['institution_name'] = 'responder'
    config['institution_logo_url'] = 'http://robohash.org/789'
    config['genesis_path'] = 'genesis.txn'

    print("#8a Initialize libvcx with new configuration")
    await vcx_init_with_config(json.dumps(config))

    print("#8a get license credential from Department of State Health Services")
    await get_license()

    print("***First responder has arrived on the scene! Responder needs to medical information from the patient!***")
    name = input("Input patient name (bob for demo purposes): ")

    print("#9a connect to patient")
    await get_patient_record(config, name)   

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())