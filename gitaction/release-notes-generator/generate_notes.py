import os
import re
import sys
import json
import subprocess
import urllib.request
from datetime import datetime

def run_command(command):
    return subprocess.check_output(command, shell=True).decode('utf-8').strip()

def main():
    # --- Configuration ---
    linear_api_key = os.environ.get('LINEAR_API_KEY')
    current_tag = os.environ.get('GITHUB_REF_NAME') # This contains the tag name

    print(f"Generating notes for tag: {current_tag}")

    # 1. Identify the Commit Range based purely on Git Tags
    try:
        # Find the previous tag immediately before the current one
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
    
    # Regex ensures number starts with 1-9 (avoids PA-0)
    id_pattern = r'([A-Z]+-[1-9][0-9]*)'

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
              identifier
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
                resp_json = json.loads(response.read().decode())
                data_obj = resp_json.get('data')
                
                if not data_obj:
                    print(f"❌ Linear API returned errors: {json.dumps(resp_json.get('errors', 'Unknown Error'))}")
                    summary_lines = []
                else:
                    nodes = data_obj.get('issues', {}).get('nodes', [])
                    for issue in nodes:
                        summary_lines.append(f"* **{issue['identifier']}**: {issue['title']} ([View]({issue['url']}))")
                        
        except Exception as e:
            print(f"Warning: Failed to fetch Linear data: {e}")

    # 5. Build Info Section
    release_author = os.environ.get('GITHUB_ACTOR', 'Unknown')
    release_time = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

    # 6. Assemble Markdown
    markdown_body = "## 🚀 Tag Info\n"
    markdown_body += f"* **Tag:** {current_tag}\n"
    markdown_body += f"* **Time:** {release_time}\n"
    markdown_body += f"* **Triggered By:** {release_author}\n\n"

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

    # 8. Output to Console
    print("\n" + "="*40)
    print("📜 GENERATED NOTES OUTPUT:")
    print("="*40)
    print(markdown_body)
    print("="*40 + "\n")
    print("Successfully generated notes based on git tags. Exiting.")
    sys.exit(0)

if __name__ == "__main__":
    main()
