#!/bin/bash
# Script to update auth-service submodule automatically
# Usage: ./update-auth-service.sh "commit message"

set -e

COMMIT_MESSAGE="$1"
if [ -z "$COMMIT_MESSAGE" ]; then
    COMMIT_MESSAGE="Update auth-service submodule"
fi

echo "🔄 Updating auth-service submodule..."
echo "📍 Strategy: full branch -> main branch (auth-service)"

# Update the submodule to latest main branch
git submodule update --remote --merge auth-service

# Check if there are changes
if git diff --quiet auth-service; then
    echo "✅ Auth-service is already up to date"
    exit 0
fi

# Add and commit the submodule update
git add auth-service
git commit -m "$COMMIT_MESSAGE"

echo "✅ Auth-service submodule updated successfully!"
echo "📝 Commit message: $COMMIT_MESSAGE"
echo "🚀 Don't forget to: git push"