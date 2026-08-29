"""Provider adapters — the only modules in the repository that speak to a vendor.

An adapter's job is narrow: send the request, return raw text plus whatever model
identity the vendor reported, and translate transport failures into
`ModelGatewayError`. Adapters do **not** parse JSON, validate schemas, build
provenance, consult the registry or record attempts — all of that is the
gateway's, and duplicating it per adapter is how the source repository ended up
with the same fail-closed logic copy-pasted across four classes and three
different admission patterns (the R10 scar: "重复的不是实现，是纪律").
"""
