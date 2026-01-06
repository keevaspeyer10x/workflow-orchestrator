#!/bin/bash
# Workflow Orchestrator - Install Script
# Run with: curl -sSL https://raw.githubusercontent.com/keevaspeyer10x/workflow-orchestrator/main/install.sh | bash

echo "Installing Workflow Orchestrator..."
pip install -q --upgrade git+https://github.com/keevaspeyer10x/workflow-orchestrator.git

echo "Enabling automatic updates for this repo..."
orchestrator setup

echo ""
echo "Quick start:"
echo "  orchestrator start \"Your task description\""
echo "  orchestrator status"
