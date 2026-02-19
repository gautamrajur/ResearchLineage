#!/bin/bash

# ResearchLineage - Create Project Structure and Push to Git

echo "Creating ResearchLineage folder structure..."

# Create all missing level 1 folders
mkdir -p models
mkdir -p notebooks
mkdir -p docs
mkdir -p deployment

echo "✓ Folders created successfully"

# Add .gitkeep files to make empty folders trackable
touch models/.gitkeep
touch notebooks/.gitkeep
touch docs/.gitkeep
touch deployment/.gitkeep

echo "✓ .gitkeep files added"

# Stage changes
git add models/ notebooks/ docs/ deployment/

echo "✓ Changes staged"

# Commit
git commit -m "chore: add project structure folders (models, notebooks, docs, deployment)"

echo "✓ Changes committed"

# Push to main
git push origin main

echo "✓ Pushed to main branch"
echo "Done! Project structure is now complete and pushed to GitHub."
