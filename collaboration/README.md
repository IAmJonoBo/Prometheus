# Collaboration scaffold

The collaboration package sketches out CRDT and presence functionality for the
future collaborative UX. Implementations delegate to Yjs, y-websocket, and other
real-time tooling but currently raise `NotImplementedError` so the surface area
is in place without heavy dependencies.
