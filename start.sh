#!/bin/bash

# Indic NLP resources ko download aur set karo
git clone https://github.com/anoopkunchukuttan/indic_nlp_resources.git

# Environment variable set karo
export INDIC_RESOURCES_PATH=$(pwd)/indic_nlp_resources

# Flask app start karo
gunicorn -b 0.0.0.0:8000 app:app
