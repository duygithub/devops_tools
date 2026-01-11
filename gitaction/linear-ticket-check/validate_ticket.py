import os
import re
import sys
import json
import urllib.request

def fail_with_comment(message):
    """
    Prints the error and attempts to post a comment to the PR if applicable.
    Then exits with status 1 to fail the build.
    """
    print(f'Failure: {message}')
    
    # Get environment variables passed from action.yml
    event = os.environ.get('EVENT_NAME')
    repo = os.environ.get('GITHUB_REPOSITORY')
    pr_num = os.environ.get('PR_NUMBER')
    token = os.environ.get('GITHUB_TOKEN')

    # Only attempt to comment if we are in a PR context and have credentials
    if event == 'pull_request' and repo and pr_num and token:
        print('Posting comment to GitHub PR...')
        url = f'https://api.github.com/repos/{repo}/issues/{pr_num}/comments'
        body_text = f'❌ **Linear Ticket Check Failed**\n\n{message}'
        data = json.dumps({'body': body_text}).encode('utf-8')
        
        req = urllib.request.Request(
            url, 
            data=data, 
            headers={
                'Authorization': f'Bearer {token}',
                'Accept': 'application/vnd.github.v3+json',
                'Content-Type': 'application/json'
            }
        )
        try:
            urllib.request.urlopen(req)
        except Exception as e:
            print(f'Warning: Could not post comment to PR. {e}')
    
    sys.exit(1)

def main():
    # --- Configuration ---
    linear_api_key = os.environ.get('LINEAR_API_KEY')
    event_name = os.environ.get('EVENT_NAME')
    
    # 1. Determine text to check based on event type
    text_to_check = ''
    check_source = ''

    if event_name == 'push':
        print('Event: Push (Checking Commit Message)')
        text_to_check = os.environ.get('COMMIT_MSG', '')
        check_source = 'Commit Message'

        # --- NEW LOGIC: Ignore Merge Commits ---
        # Standard GitHub merge commits start with these phrases
        if text_to_check.startswith('Merge pull request') or text_to_check.startswith('Merge branch'):
            print(f"Skipping validation for Merge Commit: {text_to_check}")
            sys.exit(0)
        # ---------------------------------------

    elif event_name == 'pull_request':
        pr_body = os.environ.get('PR_BODY', '')
        pr_title = os.environ.get('PR_TITLE', '')
        
        # Handle cases where body might be literal "None" string or empty
        if not pr_body or pr_body == 'None':
             pr_body = ''
        
        lines = pr_body.splitlines()
        
        if not lines:
            # Condition B: Body is empty -> Check Title
            print('Event: Pull Request (Body is empty -> Checking PR Title)')
            text_to_check = pr_title
            check_source = 'PR Title'
            
            if not text_to_check:
                 fail_with_comment('PR Description is empty and PR Title is missing/empty.')
        else:
            # Condition A: Body exists -> Check First Line
            print('Event: Pull Request (Body exists -> Checking First Line of Description)')
            text_to_check = lines[0]
            check_source = 'First line of PR Description'

    # 2. Parse Ticket ID
    # Matches 'ID: ' followed by 10+ chars
    # Example: ENG-123: Fixed the login bug
    pattern = r'^([A-Z]+-\d+):\s(.{10,})'
    match = re.search(pattern, text_to_check)

    if not match:
        fail_with_comment(f'The format in the **{check_source}** is invalid.\n\n**Found:** \"{text_to_check}\"\n**Expected:** \"ENG-123: Detailed description here...\"\n\n(Must start with ID, have a colon, and at least 10 chars of description)')

    ticket_id = match.group(1)
    print(f'Found Ticket ID: {ticket_id}')

    # 3. Call Linear API
    if not linear_api_key:
        fail_with_comment('LINEAR_API_KEY input is missing.')

    query = f'query {{ issue(id: "{ticket_id}") {{ id title }} }}'
    data = json.dumps({'query': query}).encode('utf-8')
    req = urllib.request.Request(
        'https://api.linear.app/graphql',
        data=data,
        headers={'Content-Type': 'application/json', 'Authorization': linear_api_key}
    )

    try:
        with urllib.request.urlopen(req) as response:
            resp_data = json.loads(response.read().decode())
            
            data_obj = resp_data.get('data')
            if not data_obj:
                # Linear returned an API error
                fail_with_comment(f'Linear API Error or Auth Failed.\nResponse: {json.dumps(resp_data)}')
            
            issue = data_obj.get('issue')

            if issue and issue.get('id'):
                print(f'Success! Verified ticket exists: {issue.get("title")}')
                sys.exit(0)
            else:
                fail_with_comment(f'Ticket **{ticket_id}** was not found in Linear. Please check the ID.')

    except Exception as e:
        fail_with_comment(f'Error connecting to Linear API: {e}')

if __name__ == "__main__":
    main()
