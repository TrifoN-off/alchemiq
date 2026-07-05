from alchemiq import Model
from alchemiq.types import PK
from alchemiq.types.special import Encrypted
from alchemiq.types.temporal import CreatedAt


class MigrationAccount(Model):
    id: PK[int]
    secret: Encrypted
    created_at: CreatedAt
