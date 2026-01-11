import os
import re
import sys
import json
import subprocess
import urllib.request

def run_command(command):
    return subprocess.check_output(command, shell=True).decode('utf-8').strip()

def main():
    linear_api_key = os.environ.get('LINEAR_API_KEY')
    github_token = os.environ.get('GITHUB_TOKEN')
    repo_name = os.environ.get('GITHUB_REPOSITORY') # e.g. "my-org/my-repo"
    current_tag = os.environ.get('GITHUB_REF_NAME') # e.g. "v1.0.1"

    print(f"Generating notes for {current_tag}...")

    # 1. Identify the Commit Range (Previous Tag -> Current Tag)
    try:
        # Get the previous tag reachable from HEAD (skipping the current one if it points to HEAD)
        # We use 'git describe' to find the closest tag before this one.
        prev_tag = run_command(f"git describe --tags --abbrev=0 {current_tag}^ 2>/dev/null || echo ''")
    except:
        prev_tag = ""

    if prev_tag:
        print(f"Found previous tag: {prev_tag}")
        log_range = f"{prev_tag}..{current_tag}"
    else:
        print("No previous tag found. Generating notes for entire history.")
        log_range = current_tag

    # 2. Get Commit Messages
    # Format: "CommitHash|Subject"
    git_log = run_command(f'git log {log_range} --pretty=format:"%h|%s"')
    commits = git_log.splitlines()

    # 3. Extract Linear IDs and Build Change Log
    linear_ids = set()
    change_log_lines = []
    
    # Regex to find IDs like ENG-123
    id_pattern = r'([A-Z]+-\d+)'

    for line in commits:
        if "|" not in line: continue
        hash_id, subject = line.split("|", 1)
        
        # Add to Change Log section
        change_log_lines.append(f"* {subject} ({hash_id})")
        
        # Find Linear IDs
        found = re.findall(id_pattern, subject)
        for ticket in found:
            linear_ids.add(ticket)

    # 4. Fetch Linear Titles (The "Summary" Section)
    summary_lines = []
    if linear_ids and linear_api_key:
        print(f"Fetching titles for {len(linear_ids)} tickets...")
        # Construct GraphQL query for multiple issues
        # We fetch them one by one or construct a large 'nodes' query. 
        # For simplicity in this script, we loop (or you can optimize with an 'in' filter).
        
        # Optimized: specific tickets query
        ids_string = '", "'.join(linear_ids)
        query = f"""
        query {{
          issues(filter: {{ id: {{ in: ["{ids_string}"] }} }}) {{
            nodes {{
              id
              title
              url
            }}
          }}
        }}
        """
        
        req = urllib.request.Request(
            'https://api.linear.app/graphql',
            data=json.dumps({'query': query}).encode('utf-8'),
            headers={'Content-Type': 'application/json', 'Authorization': linear_api_key}
        )

        try:
            with urllib.request.urlopen(req) as response:
                data = json.loads(response.read().decode())
                nodes = data.get('data', {}).get('issues', {}).get('nodes', [])
                for issue in nodes:
                    summary_lines.append(f"* **{issue['id']}**: {issue['title']} ([View]({issue['url']}))")
        except Exception as e:
            print(f"Warning: Failed to fetch Linear data: {e}")

    # 5. Assemble Markdown
    markdown_body = "## 📝 Summary (Linear Tickets)\n"
    if summary_lines:
        markdown_body += "\n".join(summary_lines)
    else:
        markdown_body += "No Linear tickets referenced."

    markdown_body += "\n\n## 🛠 Change Log\n"
    markdown_body += "\n".join(change_log_lines)

    # 6. Update GitHub Release
    # We need to find the Release ID associated with this tag, then update it.
    print("Updating GitHub Release...")
    
    api_base = f"https://api.github.com/repos/{repo_name}"
    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json"
    }

    # A. Get the release by tag
    try:
        req = urllib.request.Request(f"{api_base}/releases/tags/{current_tag}", headers=headers)
        with urllib.request.urlopen(req) as response:
            release_data = json.loads(response.read().decode())
            release_id = release_data['id']
            
        # B. Patch the release with new body
        update_data = json.dumps({"body": markdown_body}).encode("utf-8")
        req_update = urllib.request.Request(
            f"{api_base}/releases/{release_id}", 
            data=update_data, 
            headers=headers, 
            method="PATCH"
        )
        with urllib.request.urlopen(req_update) as response:
            print("Successfully updated Release notes!")

    except urllib.error.HTTPError as e:
        print(f"Error updating GitHub release (Tag might not have a release object yet): {e}")
        # Optional: You could create the release here if it returns 404
        sys.exit(1)

if __name__ == "__main__":
    main()
