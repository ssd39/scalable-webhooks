# Import all models here so Alembic autogenerate can detect them
from app.db.models.job import Job, JobStatus 
from app.db.models.shipment import Shipment, ShipmentStatus  
from app.db.models.invoice import Invoice 
from app.db.models.unclassified import UnclassifiedEvent
