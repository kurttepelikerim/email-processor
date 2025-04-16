import pika
import json
import re
from datasketch import MinHash, MinHashLSH
import redis
import os

# Name of the RabbitMQ queue
queue_name = 'task_queue'

# Hostname where the Redis instance is running
redis_host = os.getenv('REDIS_HOST')

# Hostname where the RabbitMQ server is running
rabbitmq_host = os.getenv('RABBITMQ_HOST')

# Redis client used to store canonical IDs, thread relationships, and metadata
redis_client = redis.Redis(host=redis_host, port=6379, db=0)

# Redis-backed MinHash LSH for near-duplicate email detection
lsh = MinHashLSH(
    threshold=0.7,
    num_perm=128,
    storage_config={
        'type': 'redis',
        'basename': b'email-lsh',
        'redis': {'host': redis_host, 'port': 6379, 'db': 0}
    }
)

def normalize_text(text):
    """
    Normalize the given text by removing specific headers, converting to lowercase,
    and stripping non-alphanumeric characters except spaces.

    :param text: the text to be normalized
    :return: the normalized text
    """

    text = re.sub(r'^(From|To|CC|Subject):\s*', '', text, flags=re.MULTILINE)
    text = text.lower()
    text = re.sub(r'[^a-z0-9\s]', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def parse_emails_from_text(text):
    """
    Parse a string of emails and return a list of the individual email bodies.

    :param text: the text to parse
    :return: a list of the individual email bodies
    """
    
    raw_emails = re.split(r'(?=^From: )', text, flags=re.MULTILINE)
    return [normalize_text(email) for email in raw_emails if email][::-1]

def get_shingles(text, n):
    """
    Get all n-shingles from the given text.

    :param text: the text to get n-shingles from
    :param n: the size of the shingles to create
    :return: a set of all n-shingles in the given text
    """
    words = text.split()
    return set(" ".join(words[i:i+n]) for i in range(len(words) - n + 1))

def compute_minhash(text, n=2, num_perm=128):
    """
    Compute a minhash for the given text.

    :param text: the text to compute a minhash for
    :param n: the size of the shingles to create
    :param num_perm: the number of permutations to use
    :return: the computed minhash
    """
    shingles = get_shingles(text, n)
    m = MinHash(num_perm=num_perm)
    for shingle in shingles:
        m.update(shingle.encode('utf8'))
    return m

def generate_canonical_id():
    """
    Generate a new canonical ID in the form "canonX", where X is an incrementing
    integer starting from 1.

    :return: the new canonical ID
    """
    new_id = redis_client.incr("canon:counter")
    return f"canon{new_id}"

def build_canonical_chain_from_text(content):
    """
    Build a canonical chain from a given text, where each canonical ID in the
    chain corresponds to a minhash of an email in the text.

    :param content: the text to build a canonical chain from
    :return: the canonical chain
    """
    emails = parse_emails_from_text(content)
    canonical_chain = []

    for email in emails:
        m = compute_minhash(email)
        candidate_ids = lsh.query(m)
        if candidate_ids:
            canonical_id = candidate_ids[0]
        else:
            canonical_id = generate_canonical_id()
            lsh.insert(canonical_id, m)
        canonical_chain.append(canonical_id)

    return canonical_chain

def update_hierarchy_and_mappings(doc_id, canonical_chain):
    """
    Given a document ID and a list of canonical IDs, update the Redis hierarchy
    data structures to reflect the new relationships.

    :param doc_id: the ID of the document
    :param canonical_chain: the list of canonical IDs
    """
    
    for i, canonical_id in enumerate(canonical_chain):
        redis_client.hset("canon_level", canonical_id, i)

    for i in range(1, len(canonical_chain)):
        parent = canonical_chain[i - 1]
        child = canonical_chain[i]
        redis_client.hset("canon_parent", child, parent)
        redis_client.sadd(f"canon_children:{parent}", child)

    final_canonical = canonical_chain[-1]
    redis_client.hset("doc_to_canon", doc_id, final_canonical)
    redis_client.sadd(f"canon_docs:{final_canonical}", doc_id)

def callback(ch, method, properties, body):
    """
    Callback function for RabbitMQ consumer. Given a message body, process it to
    build a canonical ID chain and update Redis hierarchy data structures.

    :param ch: the RabbitMQ channel
    :param method: the message method (Basic.Deliver)
    :param properties: the message properties
    :param body: the message body
    """
    
    try:
        payload = json.loads(body.decode())
        doc_id = payload["doc_id"]
        content = payload["content"]
        print(f"[>] Received: {doc_id}")

        chain = build_canonical_chain_from_text(content)
        update_hierarchy_and_mappings(doc_id, chain)

        print(f"[✔] Processed: {doc_id}")
        ch.basic_ack(delivery_tag=method.delivery_tag)

    except Exception as e:
        print(f"[!] Error processing message: {e}")

def main():
    """
    Main entry point for the script. Connects to RabbitMQ and sets up a consumer
    on the specified queue. As messages are received, the callback function is
    called to process them.
    """
    
    connection = pika.BlockingConnection(pika.ConnectionParameters(rabbitmq_host))
    channel = connection.channel()
    channel.queue_declare(queue=queue_name, durable=True)
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue=queue_name, on_message_callback=callback)
    print("[*] Waiting for tasks. To exit press CTRL+C")
    channel.start_consuming()

if __name__ == "__main__":
    main()
