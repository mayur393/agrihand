#!/usr/bin/env bash
set -euo pipefail

echo "Setting up Agrihand dev environment..."

python3.12 -m venv .venv
source .venv/bin/activate

pip install --upgrade pip
pip install kaggle-environments kaggle

echo ""
echo "Verifying installs..."
python3 -c "import kaggle_environments; print('kaggle_environments:', kaggle_environments.__version__)"
kaggle --version

echo ""
echo "Setup complete. Activate with: source .venv/bin/activate"
