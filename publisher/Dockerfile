# Use official Python image
FROM python:3.13-slim

# Set working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY assignment_data/ ./assignment_data/

# Copy the app code
COPY publisher.py .

# Run the app
CMD ["python", "publisher.py"]
