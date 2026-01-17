#!/usr/bin/env python3
# Set Railway environment variables via the Public GraphQL API.
# Usage:
#   python scripts/railway_set_vars.py --token <RAILWAY_TOKEN> --project <PROJECT_ID> --environment <ENVIRONMENT_ID> [--service <SERVICE_ID>] --env-file .env
# Endpoint: https://backboard.railway.com/graphql/v2

import argparse
from pathlib import Path
import requests

API = 'https://backboard.railway.com/graphql/v2'

MUT_COLLECTION = """
mutation variableCollectionUpsert($input: VariableCollectionUpsertInput!) {
  variableCollectionUpsert(input: $input)
}
"""

MUT_UPSERT_ONE = """
mutation variableUpsert($input: VariableUpsertInput!) {
  variableUpsert(input: $input)
}
"""

def read_env_file(path: str) -> dict:
    data = {}
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if '=' not in line:
            continue
        k, v = line.split('=', 1)
        data[k.strip()] = v.strip().strip('"')
    return data


def call_gql(token: str, query: str, variables: dict) -> dict:
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    r = requests.post(API, headers=headers, json={'query': query, 'variables': variables}, timeout=60)
    data = r.json()
    if 'errors' in data:
        raise RuntimeError(data['errors'])
    return data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--token', required=True)
    ap.add_argument('--project', required=True)
    ap.add_argument('--environment', required=True)
    ap.add_argument('--service', required=False)
    ap.add_argument('--env-file', required=True)
    args = ap.parse_args()

    vars_map = read_env_file(args.env_file)
    skip_keys = { 'ENV' }
    for k in list(vars_map.keys()):
        if k in skip_keys:
            vars_map.pop(k)

    # Try batch first
    try:
        payload = {
            'input': {
                'projectId': args.project,
                'environmentId': args.environment,
                **({'serviceId': args.service} if args.service else {}),
                'variables': vars_map
            }
        }
        _ = call_gql(args.token, MUT_COLLECTION, payload)
        print('✅ Upserted variables (batch) successfully.')
        return
    except Exception as e:
        print('Batch upsert failed, falling back to per-variable upsert...', e)

    for name, value in vars_map.items():
        payload = {
            'input': {
                'projectId': args.project,
                'environmentId': args.environment,
                **({'serviceId': args.service} if args.service else {}),
                'name': name,
                'value': value
            }
        }
        _ = call_gql(args.token, MUT_UPSERT_ONE, payload)
        print(f'  • {name} = {value[:4]}***')
    print('✅ Upserted variables (individual) successfully.')

if __name__ == '__main__':
    main()
