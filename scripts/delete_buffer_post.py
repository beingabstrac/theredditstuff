#!/usr/bin/env python3
import json
import os
import sys
import urllib.request


def gql_string(value):
    return json.dumps(value)


def main():
    api_key = os.getenv("BUFFER_API_KEY")
    post_id = os.getenv("BUFFER_POST_ID") or (sys.argv[1] if len(sys.argv) > 1 else "")
    if not api_key:
        raise RuntimeError("Missing BUFFER_API_KEY")
    if not post_id:
        raise RuntimeError("Missing Buffer post id")

    mutation = f"""
    mutation {{
      deletePost(input: {{ id: {gql_string(post_id)} }}) {{
        ... on DeletePostSuccess {{
          id
        }}
        ... on VoidMutationError {{
          message
        }}
      }}
    }}
    """
    req = urllib.request.Request(
        "https://api.buffer.com/graphql",
        data=json.dumps({"query": mutation}).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as response:
        data = json.loads(response.read().decode("utf-8"))
    if data.get("errors"):
        raise RuntimeError(json.dumps(data["errors"], indent=2))
    result = data.get("data", {}).get("deletePost", {})
    if result.get("message"):
        raise RuntimeError(result["message"])
    print(json.dumps({"deleted": result.get("id")}, indent=2))


if __name__ == "__main__":
    main()
