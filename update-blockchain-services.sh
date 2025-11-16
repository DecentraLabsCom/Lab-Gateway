#!/bin/bash
# Script to update blockchain-services submodule automatically
# Usage: ./update-blockchain-services.sh "commit message"

set -e

COMMIT_MESSAGE="$1"
if [ -z "$COMMIT_MESSAGE" ]; then
    COMMIT_MESSAGE="Update blockchain-services submodule"
fi

echo "🔄 Updating blockchain-services submodule..."
echo "📍 Strategy: full branch -> main branch (blockchain-services)"

# Update the submodule to latest main branch
git submodule update --remote --merge blockchain-services

# Check if there are changes
if git diff --quiet blockchain-services; then
    echo "✅ Blockchain-services is already up to date"
    exit 0
fi

# Add and commit the submodule update
git add blockchain-services
git commit -m "$COMMIT_MESSAGE"

echo "✅ Blockchain-services submodule updated successfully!"
echo "📝 Commit message: $COMMIT_MESSAGE"
echo "🚀 Don't forget to: git push"