"""String processing utilities for Myrcat."""

import re
from typing import List, Optional


def clean_title(title: str) -> str:
    """Clean track title by removing text in parentheses, brackets, etc.
    
    Args:
        title: Original track title
        
    Returns:
        Cleaned track title
    """
    if not title:
        return ""
    return re.split(r"[\(\[\<]", title)[0].strip()


def normalize_artist_name(artist: str) -> str:
    """Normalize an artist name for consistent matching and comparison.
    
    This function:
    1. Converts to lowercase
    2. Removes common prefixes like "The", "A", "An"
    3. Removes special characters
    4. Normalizes whitespace
    
    Args:
        artist: Original artist/band name
        
    Returns:
        Normalized artist name for comparison purposes
    """
    if not artist:
        return ""
        
    # Convert to lowercase and trim whitespace
    normalized_artist = artist.lower().strip()
    
    # Remove common prefixes
    prefixes = ["the ", "a ", "an "]
    for prefix in prefixes:
        if normalized_artist.startswith(prefix):
            normalized_artist = normalized_artist[len(prefix):]
            break
    
    # Clean special characters from artist name
    normalized_artist = re.sub(r'[^\w\s]', ' ', normalized_artist)
    
    # Replace multiple spaces with a single space
    normalized_artist = re.sub(r'\s+', ' ', normalized_artist).strip()
    
    return normalized_artist


def clean_artist_name(artist: str) -> str:
    """Clean artist name by removing featuring artists, collaborations, etc.
    
    This function is less aggressive than normalize_artist_name and preserves
    capitalization, but removes common features or collaboration parts.
    
    Args:
        artist: Original artist/band name
        
    Returns:
        Cleaned artist name suitable for display or searching
    """
    if not artist:
        return ""
        
    # Simple cleanup of artist name
    clean_artist = artist.strip()
    
    # Remove featuring artists for cleaner search
    for separator in [" feat. ", " ft. ", " featuring ", " with ", " & ", " and "]:
        if separator in clean_artist.lower():
            clean_artist = clean_artist.split(separator, 1)[0].strip()
    
    return clean_artist


def generate_artist_variations(artist_name: str) -> List[tuple]:
    """Generate variations of an artist name for improved search results.
    
    Args:
        artist_name: Original artist name
        
    Returns:
        List of (variation, description) tuples
    """
    variations = []
    
    # Add "The" prefix if not present
    if not artist_name.lower().startswith("the "):
        variations.append((f"The {artist_name}", "with 'The' prefix"))
    
    # Remove "The" prefix if present
    if artist_name.lower().startswith("the "):
        without_the = artist_name[4:].strip()
        variations.append((without_the, "without 'The' prefix"))
        
    # Add common band suffixes for solo artists
    if " & " not in artist_name.lower() and " and " not in artist_name.lower():
        variations.append((f"{artist_name} & The Band", "with '& The Band' suffix"))
        variations.append((f"{artist_name} Band", "with 'Band' suffix"))
        
    # For artists like "Noel Gallagher", check their well-known bands
    lower_name = artist_name.lower()
    if "gallagher" in lower_name and "noel" in lower_name:
        variations.append(("Noel Gallagher's High Flying Birds", "well-known project"))
        variations.append(("Oasis", "well-known band"))
    
    # Can add more special cases as needed
        
    return variations


def generate_artist_title_hash(artist: str, title: Optional[str] = None) -> str:
    """Generate a hash from artist and optional title.
    
    Args:
        artist: Artist name
        title: Optional title for artist-title pair hash
        
    Returns:
        Hash string for lookup purposes
    """
    from myrcat.utils.image import generate_hash
    
    if title is None:
        # Artist-only hash
        hash_input = normalize_artist_name(artist)
    else:
        # Artist-title pair hash
        hash_input = f"{artist}-{title}".lower()
    
    return generate_hash(hash_input)