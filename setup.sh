#!/bin/bash

# Setup script for News Monitor application

echo "=========================================="
echo "News Monitor - Setup Script"
echo "=========================================="

# Check Python version
echo "Checking Python version..."
python3 --version

# Create virtual environment
echo ""
echo "Creating virtual environment..."
python3 -m venv venv

# Activate virtual environment
echo ""
echo "Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo ""
echo "Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Copy env example if .env doesn't exist
if [ ! -f .env ]; then
    echo ""
    echo "Creating .env file from env.example..."
    cp env.example .env
    echo "✓ Created .env file"
    echo "  Please edit .env to configure your news providers"
else
    echo ""
    echo "✓ .env file already exists"
fi

# Create database directory if needed
echo ""
echo "Setup complete!"
echo ""
echo "To activate the virtual environment in the future, run:"
echo "  source venv/bin/activate"
echo ""
echo "To run the application:"
echo "  python3 main.py"
echo ""




