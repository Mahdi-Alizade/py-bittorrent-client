import hashlib

def calculate_info_hash(info_dict: dict) -> str:
    """
    Calculates the SHA1 hash of the 'info' dictionary from a torrent.
    This acts as the unique identifier for the file/swarm.
    
    Note: In strict BitTorrent specs, keys must be sorted. 
    We assume the dictionary passed here was constructed strictly.
    """
    try:
        # First, we serialize the dict back to bencoded format
        # Since Python 3.7+, dicts preserve insertion order.
        # If our dict came from the generator, keys are sorted.
        
        # Importing here to avoid circular dependency issues during import
        from .parser import TorrentEncoder
        
        encoded_info = TorrentEncoder.encode(info_dict)
        
        # Calculate SHA1
        sha1_hash = hashlib.sha1(encoded_info)
        return sha1_hash.hexdigest()
    except Exception as e:
        raise RuntimeError(f"Failed to calculate Info Hash: {e}")