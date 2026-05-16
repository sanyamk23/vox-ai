#!/bin/bash
# Script to run tests inside the backend container

echo "🚀 Running Project Vox Test Suite..."

# Ensure we are in the project root
cd "$(dirname "$0")/.."

# Check if docker is running
if ! docker info > /dev/null 2>&1; then
  echo "❌ Error: Docker is not running."
  exit 1
fi

# Sync tests to container first
docker cp backend/chat/tests/ vox-ai-backend-1:/app/chat/
docker cp backend/pytest.ini vox-ai-backend-1:/app/

# Run pytest
docker-compose exec -T backend pytest chat/tests/

RESULT=$?

if [ $RESULT -eq 0 ]; then
  echo "✅ All tests passed!"
else
  echo "❌ Some tests failed. Please check the logs above."
fi

exit $RESULT
