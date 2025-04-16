# Email Ingestion and Deduplication System

## Description

This project ingests raw email threads and deduplicates them into canonical structures. It handles challenges like duplicates, formatting variations, and reply chains by mapping emails to canonical threads and building a thread hierarchy in real time at large scale.

To run this project, you must include the assignment data (`test` and `eval` directories) in the repository root.

## Local Testing

1. Clone this repo to your machine.
2. Download Docker Desktop on your machine.
3. Build and start all services with `docker-compose up --build`.
4. Wait for the worker to finish processing. Open your browser and go to http://localhost:8080/ to view the results.


## Kubernetes Testing

This assumes you have already completed the Local Testing steps.

1. Download and install `kubectl` and Rancher Desktop.
2. Set the Kubernetes context to use Rancher Desktop:
   ```bash
   kubectl config use-context rancher-desktop
3. Tag and push the publisher Docker image to your Docker Hub account:
     ```bash
     docker tag publisher:latest <your-docker-username>/publisher:latest
     docker push <your-docker-username>/publisher:latest
     ```
4. Tag and push the worker Docker image to your Docker Hub account:
   ```bash
     docker tag worker:latest <your-docker-username>/worker:latest
     docker push <your-docker-username>/worker:latest
     ```
5. Update the `image` field in the deployment YAML files for both the publisher and worker:
   ```yaml
   image: <your-docker-username>/<service-name>:latest
6. Apply the Kubernetes deployment files from the `k8s` directory:
   ```bash
   kubectl apply -f ./k8s
7. Check that all pods have started successfully:
   ```bash
   kubectl get pods
8. Copy the name of the publisher pod (e.g., `publisher-xxxxxxxxxx-xxxxx`) and run the following command to forward the port. This allows you to access the web server at http://localhost:8000/ :
   ```bash
   kubectl port-forward publisher-xxxxxxxxxx-xxxxx 8000:8000
