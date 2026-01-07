#!/bin/bash
# Workflow Orchestrator - Install Script
# Run with: curl -sSL https://raw.githubusercontent.com/keevaspeyer10x/workflow-orchestrator/main/install.sh | bash

echo "Installing Workflow Orchestrator..."
pip install -q --upgrade git+https://github.com/keevaspeyer10x/workflow-orchestrator.git

echo "Installing review dependencies..."
pip install -q aider-chat 2>/dev/null || echo "Note: aider-chat install skipped (optional)"

echo "Enabling automatic updates for this repo..."
orchestrator setup

echo ""
echo "Ready! You can now say things like:"
echo "  'Use orchestrator to build a login page'"
echo "  'Start a workflow for fixing the search bug'"
echo "  'What's the orchestrator status?'"
