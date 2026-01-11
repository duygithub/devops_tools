import os
import re
import sys
import json
import subprocess
import urllib.request
import urllib.error
from datetime import datetime

def run_command(command):
    return subprocess.check_output(command, shell=True).decode('utf-8').strip()

def main():
    # --- Configuration ---
    linear_api_key = os.environ.get('LINEAR_API_KEY')
    github_token = os.environ.get('GITHUB_TOKEN')
    repo_name = os.environ.get('GITHUB_REPOSITORY') # e.g. "my-org/my-repo"
    current_tag = os.environ.get('GITHUB_REF_NAME') # e.g. "v1.0.1"
    
    # Check for Dry Run flag
    is_dry_run = os.environ.get('DRY_RUN', 'false').lower() == 'true'

    print(f"Generating notes for tag: {current_tag}")
    if is_dry_run:
        print("🧪 MODE: DRY RUN (No changes will be pushed to GitHub)")

    # 1. Identify the Commit Range
    try:
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
    try:
        git_log = run_command(f'git log {log_range} --pretty=format:"%h|%an|%s"')
        commits = git_log.splitlines()
    except Exception as e:
        print(f"Error fetching git log: {e}")
        sys.exit(1)

    # 3. Extract Linear IDs and Build Change Log
    linear_ids = set()
    change_log_lines = []
    id_pattern = r'([A-Z]+-\d+)'

    for line in commits:
        if "|" not in line: continue
        parts = line.split("|", 2)
        if len(parts) < 3: continue
        
        hash_id, author, subject = parts
        change_log_lines.append(f"* {subject} ({hash_id}) - @{author}")
        
        found = re.findall(id_pattern, subject)
        for ticket in found:
            linear_ids.add(ticket)

    # 4. Fetch Linear Titles
    summary_lines = []
    if linear_ids and linear_api_key:
        print(f"Fetching titles for {len(linear_ids)} tickets...")
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

    # 5. Build Release Info Section (UPDATED)
    release_branch = "Unknown"
    release_author = os.environ.get('GITHUB_ACTOR', 'Unknown')
    # Default time is "Now" (UTC) unless overridden by the event
    release_time = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    
    event_path = os.environ.get('GITHUB_EVENT_PATH')
    if event_path and os.path.exists(event_path):
        try:
            with open(event_path, 'r') as f:
                event_data = json.load(f)
            
            # Case A: Real Release Event
            if 'release' in event_data:
                release_branch = event_data['release'].get('target_commitish', release_branch)
                release_author = event_data['release'].get('author', {}).get('login', release_author)
                
                # Parse and reformat the timestamp from GitHub (e.g. 2023-10-05T14:48:00Z)
                raw_date = event_data['release'].get('created_at')
                if raw_date:
                    release_time = raw_date.replace('T', ' ').replace('Z', ' UTC')

            # Case B: Fallback for Dispatch/Push (Testing)
            else:
                # If we are testing, the "branch" is technically the ref we are on
                if release_branch == "Unknown":
                    # Try getting ref name, but if it's a tag, this will just be the tag name.
                    # This is just a hint for the dry run output.
                    release_branch = os.environ.get('GITHUB_REF_NAME', 'HEAD')

        except Exception as e:
            print(f"Warning: Could not parse event payload: {e}")

    # 6. Assemble Markdown
    markdown_body = "## 🚀 Release Info\n"
    markdown_body += f"* **Branch:** {release_branch}\n"
    markdown_body += f"* **Time:** {release_time}\n"
    markdown_body += f"* **Created By:** {release_author}\n\n"

    markdown_body += "## 📝 Summary (Linear Tickets)\n"
    if summary_lines:
        markdown_body += "\n".join(summary_lines)
    elif linear_ids:
        markdown_body += "⚠️ **Warning:** Could not fetch ticket titles (Check API Key or Logs).\n\n"
        markdown_body += "**Referenced Tickets:**\n"
        for tid in sorted(linear_ids):
            markdown_body += f"* {tid}\n"
    else:
        markdown_body += "No Linear tickets referenced."

    markdown_body += "\n\n## 🛠 Change Log\n"
    if change_log_lines:
        markdown_body += "\n".join(change_log_lines)
    else:
        markdown_body += "No commits found in this range."

    # 7. Generate Local File
    output_filename = "release_notes.md"
    try:
        with open(output_filename, "w", encoding="utf-8") as f:
            f.write(markdown_body)
        print(f"✅ Generated local file: {output_filename}")
    except Exception as e:
        print(f"Error writing local file: {e}")

    # 8. Output or Update Release
    if is_dry_run:
        print("\n" + "="*40)
        print("📜 DRY RUN OUTPUT (Markdown):")
        print("="*40)
        print(markdown_body)
        print("="*40 + "\n")
        print("Dry run complete. Exiting success.")
        sys.exit(0)

    # --- LIVE UPDATE LOGIC ---
    print("Updating GitHub Release...")
    
    api_base = f"https://api.github.com/repos/{repo_name}"
    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json"
    }

    try:
        # A. Get the release ID by tag
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
            print(f"Successfully updated Release {current_tag}!")

    except urllib.error.HTTPError as e:
        print(f"Error updating GitHub release (Tag might not have a release object yet): {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
