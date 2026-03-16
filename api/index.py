import sys
import os

# Add backend directory to path so imports resolve correctly in Vercel's Lambda
_api_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_api_dir, '..', 'backend'))

from main import app
