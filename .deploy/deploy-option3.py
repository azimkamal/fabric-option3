import os, argparse, time, requests
from azure.identity import ClientSecretCredential
 
FABRIC_API = 'https://api.fabric.microsoft.com/v1'
 
 
def get_token(credential):
    """Get a bearer token for the Fabric API."""
    scope = 'https://api.fabric.microsoft.com/.default'
    return credential.get_token(scope).token
 
 
def deploy_stage(token, pipeline_id, source_stage_id, note=''):
    """
    Trigger a deployment from source_stage to the next stage.
    Uses the Fabric Deploy Stage Content API.
    Returns the operation ID for polling.
    """
    url = f'{FABRIC_API}/deploymentPipelines/{pipeline_id}/stages/{source_stage_id}/deploy'
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    body = {
        'note': note,
        # To deploy all items leave 'items' out of the body.
        # For selective deploy, add:
        # 'items': [{'type': 'Notebook', 'sourceId': '<item-id>'}]
    }
    response = requests.post(url, headers=headers, json=body)
    if response.status_code in (200, 202):
        # 202 Accepted — async operation, get operation ID from header
        op_id = response.headers.get('x-ms-operation-id')
        print(f'  Deployment triggered. Operation ID: {op_id}')
        return op_id
    else:
        raise Exception(f'Deploy failed: {response.status_code} {response.text}')
 
 
def poll_operation(token, op_id, timeout=600, interval=10):
    """
    Poll the Long Running Operation until it completes.
    Raises an exception if it fails or times out.
    """
    url = f'{FABRIC_API}/operations/{op_id}'
    headers = {'Authorization': f'Bearer {token}'}
    elapsed = 0
    while elapsed < timeout:
        response = requests.get(url, headers=headers)
        data = response.json()
        status = data.get('status', 'Unknown')
        print(f'  Operation status: {status} ({elapsed}s elapsed)')
        if status == 'Succeeded':
            print('  Deployment completed successfully.')
            return
        elif status in ('Failed', 'Cancelled'):
            raise Exception(f'Deployment {status}: {data}')
        time.sleep(interval)
        elapsed += interval
    raise Exception(f'Deployment timed out after {timeout}s')
 
 
# ── Argument parser ─────────────────────────────────────────
parser = argparse.ArgumentParser()
parser.add_argument('--aztenantid',       type=str)
parser.add_argument('--azclientid',       type=str)
parser.add_argument('--azspsecret',       type=str)
parser.add_argument('--pipeline_id',      type=str)
parser.add_argument('--dev_stage_id',     type=str)
parser.add_argument('--test_stage_id',    type=str)
parser.add_argument('--prod_stage_id',    type=str)
parser.add_argument('--target',           type=str,
                    help='test | prod | both (default: both)')
args = parser.parse_args()
 
# ── Authentication ───────────────────────────────────────────
credential = ClientSecretCredential(
    client_id=args.azclientid,
    client_secret=args.azspsecret,
    tenant_id=args.aztenantid,
)
token = get_token(credential)
print(f'  Authenticated successfully.')
print(f'  Pipeline ID  : {args.pipeline_id}')
print(f'  Target       : {args.target}')
 
target = args.target or 'both'
 
# ── Deploy Dev → Test ────────────────────────────────────────
if target in ('test', 'both'):
    print('\n--- Deploying Dev → Test ---')
    op_id = deploy_stage(
        token, args.pipeline_id, args.dev_stage_id,
        note='Automated deployment via GitHub Actions'
    )
    poll_operation(token, op_id)
 
# ── Deploy Test → Prod ───────────────────────────────────────
if target in ('prod', 'both'):
    print('\n--- Deploying Test → Prod ---')
    # Refresh token before Prod deploy (long-running workflows)
    token = get_token(credential)
    op_id = deploy_stage(
        token, args.pipeline_id, args.test_stage_id,
        note='Automated deployment via GitHub Actions'
    )
    poll_operation(token, op_id)
 
print('\nAll deployments completed.')
