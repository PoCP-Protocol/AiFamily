"""Infrastructure layer: the two `ServiceRepositoryPort` implementations.

`fake_repository` is dict-backed and used by the acceptance tests to prove the
application layer depends on the port. `sqlalchemy_repository` maps onto the
tables `database/baseline/0035_family_service_booking_objects.sql` defines (plus
the one new table for private check-in drafts).
"""
