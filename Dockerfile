# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install ffmpeg for pydub
RUN apt-get update && apt-get install -y ffmpeg && apt-get clean

# Copy the rest of the application
COPY . .

# Expose port
EXPOSE 10000

# Command to run the application
CMD ["python", "app.py"]
