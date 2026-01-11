This repo contains free tools that can help improve the build process.
* Linear Ticket Check - Checks that the commit / PR message must contain the appropriate Linear Ticket

# Linear Ticket Check
**Location:** gitaction/linear-ticket-check

## Summary
This action checks that the linear ticket should exist in a checkin. There are two ways to pass this check:
* The commit message must contain the linear ticket at the start of the commit message.
* The description of the PR must contain the commit message.

**For commits:**
* Has to start with the ticket id followed by a colon
* Must be text after the colon of at least 10 characters.

**For PR's:**
* Must be at least 1 line (can have as many lines as you want)
* A line must either start with the linear ticket id, a *, or be an empty line
*  The line that starts with a linear ticket id must have a colon and at least 10 characters (similar rule to commit).
*  The first line must be the line with a linear ticket id
* The check will add the failure reason to the PR comment and block a merge.

## Usage
Add the following to your .github/workflows/your_file_name.yml
```
steps:
  - uses: actions/checkout@v4
  
  - uses: duygithub/devops_tools/gitaction/linear-ticket-check@1.0.0
    with:
      linear-api-key: ${{ secrets.LINEAR_API_KEY }}
      github-token: ${{ secrets.GITHUB_TOKEN }}
```
