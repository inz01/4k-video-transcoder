from rq import Queue, Worker

from app.job_queue import redis_conn

listen = ["transcode"]


if __name__ == "__main__":
    queues = [Queue(name, connection=redis_conn) for name in listen]
    worker = Worker(queues, connection=redis_conn)
    worker.work()
