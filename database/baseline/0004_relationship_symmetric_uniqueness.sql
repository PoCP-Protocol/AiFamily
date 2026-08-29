-- 0004_relationship_symmetric_uniqueness — Prevent reverse duplicates for symmetric relationships.
-- Keeps directional uniqueness for PARENT_CHILD, GUARDIAN_CHILD, and OTHER.
CREATE UNIQUE INDEX IF NOT EXISTS uq_relationship_symmetric_pair
ON family_relationships(
  family_id,
  LEAST(person_a_id, person_b_id),
  GREATEST(person_a_id, person_b_id),
  relationship_type
)
WHERE relationship_type IN ('SPOUSE', 'SIBLING');