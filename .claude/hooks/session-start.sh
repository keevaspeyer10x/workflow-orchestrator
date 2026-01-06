#!/bin/bash
# Auto-install/update workflow orchestrator

#!/bin/bash
# Auto-install/update workflow orchestrator
# Added by: orchestrator install-hook
echo "Checking workflow orchestrator..."
pip install -q --upgrade git+https://github.com/keevaspeyer10x/workflow-orchestrator.git
