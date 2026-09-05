import CatalogExperienceScreen from "../catalog-experience";

// Product catalogue is the product-only projection of the same need-first
// discovery journey; it deliberately keeps the API and state contract intact.
export default function ProductCatalogRoute() {
  return <CatalogExperienceScreen mode="products" />;
}
