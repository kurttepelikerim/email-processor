import pika
import os
import json
import time
import redis
from http.server import HTTPServer, SimpleHTTPRequestHandler

# Name of the RabbitMQ queue
queue_name = 'task_queue'

# Hostname where the Redis instance is running
redis_host = os.getenv('REDIS_HOST')

# Hostname where the RabbitMQ server is running
rabbitmq_host = os.getenv('RABBITMQ_HOST')

# Subdirectory under 'assignment_data/' corresponding to either 'test' or 'eval'
work_dir = os.getenv('WORKDIR')

# Full path to the directory containing email data
data_dir = f"assignment_data/{work_dir}/"

# Redis client used to store canonical IDs, thread relationships, and metadata
redis_client = redis.Redis(host=redis_host, port=6379, db=0)

def send_files_to_queue(channel):
    """
    Publishes all files in the evaluation directory to the RabbitMQ queue for processing

    :param channel: A connected RabbitMQ channel
    """
    
    for filename in sorted(os.listdir(data_dir)):
        if filename.endswith('.txt'):
            filepath = os.path.join(data_dir, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
            except UnicodeDecodeError:
                with open(filepath, "r", encoding="cp1252") as f:
                    content = f.read()
            except Exception as e:
                print(f"Error reading {filename}: {e}")

            payload = {
                "doc_id": filename,
                "content": content
            }

            channel.basic_publish(
                exchange='',
                routing_key=queue_name,
                body=json.dumps(payload),
                properties=pika.BasicProperties(delivery_mode=2)
            )
            print(f"[x] Sent: {filename}")

def wait_until_queue_empty(channel):
    """
    Blocks until the task queue is empty.

    :param channel: A connected RabbitMQ channel
    """
    while True:
        q = channel.queue_declare(queue=queue_name, durable=True, passive=True)
        if q.method.message_count == 0:
            break
        time.sleep(1)

def save_canonical_threads():
    """
    Saves the canonical threads in a file named canonical_threads.txt.
    Each line consists of a canonical ID followed by the IDs of the documents in the thread.
    """
    canon_keys = redis_client.keys("canon_docs:*")
    canon_keys = sorted(
        canon_keys,
        key=lambda k: int(k.decode().split(":")[1].replace("canon", ""))
    )

    output = []
    for canon_key in canon_keys:
        canon_id = canon_key.decode().split(":")[1]
        docs = sorted(doc.decode() for doc in redis_client.smembers(canon_key))
        output.append(f"{canon_id}:")
        for doc in docs:
            output.append(f"\t- {doc}")
    os.makedirs("docs", exist_ok=True)
    with open("docs/canonical_threads.txt", "w") as f:
        f.write("\n".join(output))

def save_hierarchical_structure():
    """
    Saves the hierarchical structure of canonical threads in a file named hierarchical_structure.txt.
    Each line consists of a canonical thread, represented as a chain of canonical IDs, joined by " → ".
    """
    level_data = redis_client.hgetall("canon_level")

    roots = [
        key.decode() for key, val in level_data.items()
        if val.decode() == "0"
    ]

    def dfs(path, current, chains):
        children = redis_client.smembers(f"canon_children:{current}")
        if not children:
            chains.append(path)
            return
        for child in sorted([c.decode() for c in children], key=lambda x: int(x.replace("canon", ""))):
            dfs(path + [child], child, chains)

    all_chains = []
    for root in sorted(roots, key=lambda x: int(x.replace("canon", ""))):
        dfs([root], root, all_chains)
    os.makedirs("docs", exist_ok=True)
    with open("docs/hierarchical_structure.txt", "w") as f:
        for chain in all_chains:
            f.write(" -> ".join(chain) + "\n")

def start_web_server():
    """
    Main entry point for the results web server. Starts a web server serving the generated
    canonical_threads.txt and hierarchical_structure.txt files.
    """
    print("Starting web server on port 8000...")
    os.chdir("docs")
    httpd = HTTPServer(('0.0.0.0', 8000), SimpleHTTPRequestHandler)
    httpd.serve_forever()

def main():
    """
    Main entry point for the script. Connects to RabbitMQ, sends all evaluation
    files to the queue for processing, waits until the queue is empty, saves the
    canonical threads and hierarchical structure to text files.
    """
    connection = pika.BlockingConnection(pika.ConnectionParameters(rabbitmq_host))
    channel = connection.channel()
    channel.queue_declare(queue=queue_name, durable=True)

    send_files_to_queue(channel)
    wait_until_queue_empty(channel)
    time.sleep(3)

    save_canonical_threads()
    save_hierarchical_structure()

    connection.close()

if __name__ == "__main__":
    main()
    start_web_server()
