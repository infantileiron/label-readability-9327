import os

DATABASE_URL = os.environ['DATABASE_URL']
REDIS_URL = os.getenv('REDIS_URL', 'redis://redis:6379/0')
JWT_SECRET = os.environ['JWT_SECRET']
HEARTBEAT = 'label-readability:worker:heartbeat'
BATCH_SECONDS = float(os.getenv('BATCH_SECONDS', '2.5'))
STEP_BUDGET = int(os.getenv('STEP_BUDGET', '400000'))
