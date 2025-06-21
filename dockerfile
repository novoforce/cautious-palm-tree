# Use the official Python image from the Docker Hub with the specified version
FROM python:3.10.18-slim

# Set the working directory in the container
WORKDIR /application

# Copy the requirements file into the container at /application
COPY requirements.txt .

# Install any dependencies specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the content of the local app directory to the working directory in the container
COPY . .

# Expose the port that the app runs on
EXPOSE 8000

# Command to run the FastAPI app with uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
