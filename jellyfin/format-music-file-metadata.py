#!/usr/bin/env python3

import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path
import argparse
import shutil
from datetime import datetime
from mutagen import File
from mutagen.mp4 import MP4
from mutagen.aiff import AIFF
from mutagen.flac import FLAC
from mutagen.mp3 import MP3
from mutagen.oggvorbis import OggVorbis
from mutagen.wave import WAVE


def parse_artists(artist_string):
    """Parse artist string and split multiple artists."""
    if not artist_string:
        return []
    
    patterns = [
        r'\s+feat\.?\s+',
        r'\s+ft\.?\s+',
        r'\s+featuring\s+',
        r'\s+Feat\.?\s+',
        r'\s+Ft\.?\s+',
        r'\s+Featuring\s+',
    ]
    
    result = artist_string
    for pattern in patterns:
        result = re.sub(pattern, ', ', result, flags=re.IGNORECASE)

    result = re.sub(r'\s+&\s+', ', ', result)
    result = re.sub(r'\s+and\s+', ', ', result, flags=re.IGNORECASE)
    
    artists = [a.strip() for a in result.split(',')]
    artists = [a for a in artists if a]
    
    return artists


def format_artists_to_semicolon(artists_list):
    """Format artist list to semicolon-separated string."""
    return ';'.join(artists_list)


def update_nfo_file(nfo_path, dry_run=False, backup=True):
    """Update artist metadata in NFO file."""
    try:
        tree = ET.parse(nfo_path)
        root = tree.getroot()
        
        changed = False
        
        # Update all artist elements
        artist_elements = root.findall('.//artist')
        for artist_elem in artist_elements:
            if artist_elem.text:
                original = artist_elem.text.strip()
                artists = parse_artists(original)
                formatted = format_artists_to_semicolon(artists)
                
                if formatted != original:
                    if not dry_run:
                        artist_elem.text = formatted
                    changed = True
                    print(f"    Artist: '{original}' → '{formatted}'")
        
        # Update albumartist elements if they exist
        albumartist_elements = root.findall('.//albumartist')
        for albumartist_elem in albumartist_elements:
            if albumartist_elem.text:
                original = albumartist_elem.text.strip()
                artists = parse_artists(original)
                formatted = format_artists_to_semicolon(artists)
                
                if formatted != original:
                    if not dry_run:
                        albumartist_elem.text = formatted
                    changed = True
                    print(f"    Album Artist: '{original}' → '{formatted}'")
        
        if changed and not dry_run:
            if backup:
                backup_path = str(nfo_path) + f'.backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}'
                shutil.copy2(nfo_path, backup_path)
            
            ET.indent(tree, space="  ")
            tree.write(nfo_path, encoding='utf-8', xml_declaration=True)
            return True, True, "Updated successfully"
        elif changed and dry_run:
            return True, True, "Would be updated (dry run)"
        else:
            return True, False, "No changes needed"
            
    except ET.ParseError as e:
        return False, False, f"XML parse error: {e}"
    except Exception as e:
        return False, False, f"Error: {e}"


def get_current_artist(audio_file):
    """Get current artist from audio file."""
    try:
        if isinstance(audio_file, MP4):
            # M4A files use '\xa9ART' key
            if '\xa9ART' in audio_file:
                return audio_file['\xa9ART'][0]
        elif isinstance(audio_file, (FLAC, OggVorbis)):
            # FLAC and OGG use 'artist' key
            if 'artist' in audio_file:
                return audio_file['artist'][0]
        elif isinstance(audio_file, MP3):
            # MP3 uses TPE1 frame
            if audio_file.tags and 'TPE1' in audio_file.tags:
                return str(audio_file.tags['TPE1'])
        elif isinstance(audio_file, AIFF):
            # AIFF uses ID3 tags
            if audio_file.tags and 'TPE1' in audio_file.tags:
                return str(audio_file.tags['TPE1'])
        elif isinstance(audio_file, WAVE):
            # WAV with ID3 tags
            if audio_file.tags and 'TPE1' in audio_file.tags:
                return str(audio_file.tags['TPE1'])
    except Exception as e:
        print(f"    Warning: Error reading artist: {e}")
    
    return None


def get_current_album_artist(audio_file):
    """Get current album artist from audio file."""
    try:
        if isinstance(audio_file, MP4):
            # M4A files use 'aART' key
            if 'aART' in audio_file:
                return audio_file['aART'][0]
        elif isinstance(audio_file, (FLAC, OggVorbis)):
            # FLAC and OGG use 'albumartist' key
            if 'albumartist' in audio_file:
                return audio_file['albumartist'][0]
        elif isinstance(audio_file, MP3):
            # MP3 uses TPE2 frame
            if audio_file.tags and 'TPE2' in audio_file.tags:
                return str(audio_file.tags['TPE2'])
        elif isinstance(audio_file, AIFF):
            # AIFF uses ID3 tags
            if audio_file.tags and 'TPE2' in audio_file.tags:
                return str(audio_file.tags['TPE2'])
        elif isinstance(audio_file, WAVE):
            # WAV with ID3 tags
            if audio_file.tags and 'TPE2' in audio_file.tags:
                return str(audio_file.tags['TPE2'])
    except Exception as e:
        print(f"    Warning: Error reading album artist: {e}")
    
    return None


def update_artist(audio_file, artists_list):
    """Update artist field in audio file."""
    try:
        if isinstance(audio_file, MP4):
            # M4A files - use semicolon-separated string
            audio_file['\xa9ART'] = [';'.join(artists_list)]
            return True
            
        elif isinstance(audio_file, (FLAC, OggVorbis)):
            # FLAC and OGG - can handle list of artists
            audio_file['artist'] = artists_list
            return True
            
        elif isinstance(audio_file, MP3):
            # MP3 - use semicolon-separated string
            from mutagen.id3 import TPE1
            if not audio_file.tags:
                audio_file.add_tags()
            audio_file.tags['TPE1'] = TPE1(encoding=3, text=';'.join(artists_list))
            return True
            
        elif isinstance(audio_file, AIFF):
            # AIFF with ID3 tags
            from mutagen.id3 import TPE1
            if not audio_file.tags:
                audio_file.add_tags()
            audio_file.tags['TPE1'] = TPE1(encoding=3, text=';'.join(artists_list))
            return True
            
        elif isinstance(audio_file, WAVE):
            # WAV with ID3 tags
            from mutagen.id3 import TPE1
            if not audio_file.tags:
                audio_file.add_tags()
            audio_file.tags['TPE1'] = TPE1(encoding=3, text=';'.join(artists_list))
            return True
            
    except Exception as e:
        print(f"    Error updating artist: {e}")
        return False
    
    return False


def update_album_artist(audio_file, artists_list):
    """Update album artist field in audio file."""
    try:
        if isinstance(audio_file, MP4):
            # M4A files - use semicolon-separated string
            audio_file['aART'] = [';'.join(artists_list)]
            return True
            
        elif isinstance(audio_file, (FLAC, OggVorbis)):
            # FLAC and OGG - can handle list of artists
            audio_file['albumartist'] = artists_list
            return True
            
        elif isinstance(audio_file, MP3):
            # MP3 - use semicolon-separated string
            from mutagen.id3 import TPE2
            if not audio_file.tags:
                audio_file.add_tags()
            audio_file.tags['TPE2'] = TPE2(encoding=3, text=';'.join(artists_list))
            return True
            
        elif isinstance(audio_file, AIFF):
            # AIFF with ID3 tags
            from mutagen.id3 import TPE2
            if not audio_file.tags:
                audio_file.add_tags()
            audio_file.tags['TPE2'] = TPE2(encoding=3, text=';'.join(artists_list))
            return True
            
        elif isinstance(audio_file, WAVE):
            # WAV with ID3 tags
            from mutagen.id3 import TPE2
            if not audio_file.tags:
                audio_file.add_tags()
            audio_file.tags['TPE2'] = TPE2(encoding=3, text=';'.join(artists_list))
            return True
            
    except Exception as e:
        print(f"    Error updating album artist: {e}")
        return False
    
    return False


def update_music_file(file_path, dry_run=False, backup=True):
    """Update artist metadata in a music file."""
    try:
        audio = File(file_path)
        
        if audio is None:
            return True, False, "Unsupported file format"
        
        current_artist = get_current_artist(audio)
        current_album_artist = get_current_album_artist(audio)
        
        changed = False
        
        # Process artist field
        if current_artist:
            artists = parse_artists(current_artist)
            
            # Check if any changes would be made
            if isinstance(audio, (FLAC, OggVorbis)):
                would_change = len(artists) > 1 or current_artist != artists[0] if artists else False
            else:
                new_format = ';'.join(artists)
                would_change = new_format != current_artist
            
            if would_change:
                if isinstance(audio, (FLAC, OggVorbis)):
                    new_format = str(artists)
                else:
                    new_format = ';'.join(artists)
                
                print(f"    Artist: '{current_artist}' → '{new_format}'")
                
                if not dry_run:
                    if update_artist(audio, artists):
                        changed = True
                    else:
                        return False, False, "Failed to update artist"
                else:
                    changed = True
        
        # Process album artist field
        if current_album_artist:
            album_artists = parse_artists(current_album_artist)
            
            # Check if any changes would be made
            if isinstance(audio, (FLAC, OggVorbis)):
                would_change_aa = len(album_artists) > 1 or current_album_artist != album_artists[0] if album_artists else False
            else:
                new_format_aa = ';'.join(album_artists)
                would_change_aa = new_format_aa != current_album_artist
            
            if would_change_aa:
                if isinstance(audio, (FLAC, OggVorbis)):
                    new_format_aa = str(album_artists)
                else:
                    new_format_aa = ';'.join(album_artists)
                
                print(f"    Album Artist: '{current_album_artist}' → '{new_format_aa}'")
                
                if not dry_run:
                    if update_album_artist(audio, album_artists):
                        changed = True
                    else:
                        return False, False, "Failed to update album artist"
                else:
                    changed = True
        
        if not changed:
            return True, False, "No changes needed"
        
        if not dry_run:
            if backup:
                backup_path = str(file_path) + f'.backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}'
                shutil.copy2(file_path, backup_path)
            
            audio.save()
            return True, True, "Updated successfully"
        else:
            return True, True, "Would be updated (dry run)"
            
    except Exception as e:
        return False, False, f"Error: {e}"


def process_directory(music_dir, dry_run=False, backup=True, extensions=None, update_nfo=True):
    """Process all music files and NFO files in directory."""
    music_path = Path(music_dir)
    
    if not music_path.exists():
        print(f"Error: Directory '{music_dir}' does not exist!")
        return
    
    # Default supported extensions
    if extensions is None:
        extensions = ['.m4a', '.aiff', '.aif', '.flac', '.mp3', '.ogg', '.opus', '.wav']
    
    # Find all music files
    music_files = []
    for ext in extensions:
        music_files.extend(music_path.rglob(f'*{ext}'))
    
    # Find all NFO files if requested
    nfo_files = []
    if update_nfo:
        nfo_files = list(music_path.rglob('*.nfo'))
    
    total_files = len(music_files) + len(nfo_files)
    
    if total_files == 0:
        print(f"No music or NFO files found in '{music_dir}'")
        return
    
    print(f"Found {len(music_files)} music file(s) and {len(nfo_files)} NFO file(s)")
    if dry_run:
        print("Running in DRY RUN mode - no files will be modified")
    if backup:
        print("Backup enabled - original files will be preserved")
    print()
    
    stats = {'processed': 0, 'updated': 0, 'errors': 0, 'skipped': 0}
    
    # Process NFO files first
    if nfo_files:
        print("=" * 60)
        print("PROCESSING NFO FILES")
        print("=" * 60)
        for nfo_file in nfo_files:
            print(f"\nProcessing: {nfo_file}")
            success, changed, message = update_nfo_file(nfo_file, dry_run, backup)
            
            stats['processed'] += 1
            if success and changed:
                stats['updated'] += 1
            elif success and not changed:
                stats['skipped'] += 1
            else:
                stats['errors'] += 1
                print(f"    ERROR: {message}")
    
    # Process music files
    if music_files:
        print("\n" + "=" * 60)
        print("PROCESSING MUSIC FILES")
        print("=" * 60)
        for music_file in music_files:
            print(f"\nProcessing: {music_file.name}")
            success, changed, message = update_music_file(music_file, dry_run, backup)
            
            stats['processed'] += 1
            if success and changed:
                stats['updated'] += 1
            elif success and not changed:
                stats['skipped'] += 1
            else:
                stats['errors'] += 1
                print(f"    ERROR: {message}")
    
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"Files processed: {stats['processed']}")
    print(f"Files updated:   {stats['updated']}")
    print(f"Files skipped:   {stats['skipped']}")
    print(f"Errors:          {stats['errors']}")
    
    if dry_run and stats['updated'] > 0:
        print("\nThis was a dry run. Run without --dry-run to apply changes.")


def main():
    parser = argparse.ArgumentParser(
        description='Update artist metadata in music files and NFO files (M4A, AIFF, FLAC, MP3, etc.)'
    )
    parser.add_argument(
        'music_dir',
        help='Path to your music library directory'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be changed without actually modifying files'
    )
    parser.add_argument(
        '--no-backup',
        action='store_true',
        help='Skip creating backup files (not recommended)'
    )
    parser.add_argument(
        '--extensions',
        nargs='+',
        help='Specific file extensions to process (e.g., .m4a .aiff)'
    )
    parser.add_argument(
        '--skip-nfo',
        action='store_true',
        help='Skip processing NFO files'
    )
    
    args = parser.parse_args()
    
    process_directory(
        args.music_dir,
        dry_run=args.dry_run,
        backup=not args.no_backup,
        extensions=args.extensions,
        update_nfo=not args.skip_nfo
    )


if __name__ == '__main__':
    main()
