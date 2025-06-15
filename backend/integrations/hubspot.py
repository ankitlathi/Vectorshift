import json
import secrets
from fastapi import Request, HTTPException
from fastapi.responses import HTMLResponse
import httpx
import asyncio
import base64

import requests
from integrations.integration_item import IntegrationItem

from redis_client import add_key_value_redis, get_value_redis, delete_key_redis

CLIENT_ID = 'ac8e6fa6-548e-47e2-bc8a-578a2174fb38'
CLIENT_SECRET = '7119b312-5f8b-49d1-9109-3e36da021ff7'
REDIRECT_URI = 'http://localhost:8000/integrations/hubspot/oauth2callback'
SCOPES = "crm.objects.contacts.read crm.objects.contacts.write oauth"
authorization_url = f"https://app.hubspot.com/oauth/authorize?client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}&response_type=code&scope={SCOPES}"
encoded_client_id_secret = base64.b64encode(f'{CLIENT_ID}:{CLIENT_SECRET}'.encode()).decode()



async def authorize_hubspot(user_id, org_id):
    state_data = {
        'state' : secrets.token_urlsafe(32),
        'user_id' : user_id,
        'org_id' : org_id
    }
    encoded_state = json.dumps(state_data)
    await add_key_value_redis(f'hubspot_state:{org_id}:{user_id}', encoded_state, expire=600)
    
    return f'{authorization_url}&state={encoded_state}'

    
    
async def oauth2callback_hubspot(request: Request):
    if request.query_params.get('error'):
        raise HTTPException(status_code=400, detail=request.query_params.get('error_description'))

    code = request.query_params.get('code')
    encoded_state = request.query_params.get('state')
    state_data = json.loads(encoded_state)
    
    original_state = state_data.get('state')
    user_id = state_data.get('user_id')
    org_id = state_data.get("org_id")
    
    saved_state = await get_value_redis(f"hubspot_state:{org_id}:{user_id}")
    
    if not saved_state or original_state != json.loads(saved_state).get('state'):
        raise HTTPException(status_code=400, detail='State does not match.')
    
    async with httpx.AsyncClient() as client:
        response, _ = await asyncio.gather(
            client.post(
                'https://api.hubapi.com/oauth/v1/token',
                data={
                    'grant_type': 'authorization_code',
                    'code': code,
                    'redirect_uri': REDIRECT_URI,
                    'client_id': CLIENT_ID,
                    'client_secret': CLIENT_SECRET,
                },
                headers={
                    'Authorization': f'Basic {encoded_client_id_secret}',
                    'Content-Type': 'application/x-www-form-urlencoded',
                }
            ),
            delete_key_redis(f"notion_state:{org_id}:{user_id}"),
        )
    
    await add_key_value_redis(f'hubspot_credentials:{org_id}:{user_id}', json.dumps(response.json()), expire=600)
    close_window_script = """
    <html>
        <script>
            window.close();
        </script>
    </html>
    """
    return HTMLResponse(content=close_window_script)


async def get_hubspot_credentials(user_id, org_id):
    credentials = await get_value_redis(f"hubspot_credentials:{org_id}:{user_id}")
    if not credentials:
        raise HTTPException(status_code = 400, detail = "No Credentials Found")
    credentials = json.loads(credentials)
    if not credentials:
        raise HTTPException(status_code = 400, detail = "No Credentials Found")
    await delete_key_redis(f"hubspot_credentials:{org_id}:{user_id}")
    
    return credentials



def create_integration_item_metadata_object(response_json: str, item_type: str, parent_id = None, parent_name=None) -> IntegrationItem:
    parent_id = None if parent_id is None else parent_id + '_Base'
    integration_item_metadata = IntegrationItem(
        id = response_json.get('id', None) + '_' + item_type,
        name = response_json.get('name',None),
        type = item_type,
        parent_id = parent_id,
        parent_path_or_name = parent_name
    )
    
    return integration_item_metadata

def fetch_items_hubspot(
    access_token: str, url: str, aggregated_response: list, offset = None
    ) -> dict:
    params = {'offset': offset} if offset is not None else {}
    headers = {'Authorization': f"Bearer {access_token}"}
    response = requests.get(url, headers=headers, params=params)
    
    if response.status_code == 200:
        response_json = response.json()
        results = response_json.get('results', [])
        paging = response_json.get('paging', {})
        next_after = paging.get('next', {}).get('after', None)
        
        for item in results:
            aggregated_response.append(item)
        
        if next_after is not None:
            # Recursively fetch next page
            fetch_items_hubspot(access_token, url, aggregated_response, next_after)
    else:
        raise Exception(f"Failed to fetch items from HubSpot. Status code: {response.status_code}")

    
    


async def get_items_hubspot(credentials) -> list[IntegrationItem] :
    credentials = json.loads(credentials)
    url = 'https://api.hubapi.com/crm/v3/objects/contacts'
    headers = {
        'Authorization': f"Bearer {credentials.get('access_token')}",
        'Content-Type': 'application/json'
    }

    list_of_integration_item_metadata = []
    after = None  # for pagination

    while True:
        params = {'limit': 50}
        if after:
            params['after'] = after

        response = requests.get(url, headers=headers, params=params)
        if response.status_code != 200:
            raise Exception(f"Failed to fetch contacts. Status code: {response.status_code}")

        response_json = response.json()
        results = response_json.get('results', [])

        for contact in results:
            props = contact.get('properties', {})
            full_name = f"{props.get('firstname', '')} {props.get('lastname', '')}".strip()

            integration_item_metadata = IntegrationItem(
                id=contact.get('id') + '_Contact',
                name=full_name if full_name else props.get('email', 'Unknown'),
                type='Contact',
                parent_id=None,
                parent_path_or_name=None
            )
            list_of_integration_item_metadata.append(integration_item_metadata)

        # Check if there is next page
        paging = response_json.get('paging', {})
        after = paging.get('next', {}).get('after', None)
        if not after:
            break

    print(f'list_of_integration_item_metadata: {list_of_integration_item_metadata}')
    return [
    {"id": item.id, "name": item.name, "type": item.type, "parent_id": item.parent_id, "parent_name": item.parent_path_or_name}
    for item in list_of_integration_item_metadata
    ]


