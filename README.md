This is just a collection of pipes and filters that I use or maintain.

# Known issue
* As of version 1.0.0 of add_metadata.py, the user specified is indeed passed to langfuse and litellm. But the rest of the metadata are not. If anyone knows how to fix this please tell me!

## Notes:
- I'm not using anymore `pipes/costtrackingpipe/costtrackingpipe.py` because I switched to instead using langfuse, where I only need to set the user via a filter.
