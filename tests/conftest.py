import sys
import os

# Add the src directory to the Python path so tests can find it
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))
