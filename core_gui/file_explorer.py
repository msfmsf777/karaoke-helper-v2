# file_explorer.py
import os

class FileExplorer:
    """Manages the state and logic for the file explorer."""
    def __init__(self):
        self.current_folder = None
        self.instrumental_path = None
        self.vocal_path = None
        self.instrumental_selection_name = None
        self.vocal_selection_name = None

    def scan_folder(self, folder_path):
        """
        Scans a folder for valid audio files and subdirectories.
        Returns two sorted lists: subdirectories and files.
        """
        subdirs = []
        files = []
        try:
            if folder_path and os.path.isdir(folder_path):
                # Extend recognized audio formats to include common container/encodings
                # that our loader (pydub/ffmpeg fallback) handles.
                accepted = ('.wav', '.mp3', '.flac', '.m4a', '.aac', '.ogg', '.opus', '.wma')
                for entry in os.scandir(folder_path):
                    if entry.is_dir():
                        subdirs.append(entry.name)
                    else:
                        name_lower = entry.name.lower()
                        if name_lower.endswith(accepted):
                            files.append(entry.name)
                subdirs.sort()
                files.sort()
        except Exception as e:
            # Keep simple debug output to console; do not crash the UI.
            print(f"Error scanning folder '{folder_path}': {e}")
        return subdirs, files

    def set_current_folder(self, folder_path):
        """Sets the current folder and clears old selections."""
        self.current_folder = os.path.normpath(folder_path) if folder_path else None
        self.clear_selections()

    def clear_selections(self):
        """Clears the current instrumental and vocal selections."""
        self.instrumental_path = None
        self.vocal_path = None
        self.instrumental_selection_name = None
        self.vocal_selection_name = None

    def set_instrumental(self, selected_filename):
        if self.current_folder and selected_filename:
            if selected_filename == self.vocal_selection_name:
                self.vocal_selection_name = None
                self.vocal_path = None

            self.instrumental_selection_name = selected_filename
            self.instrumental_path = os.path.join(self.current_folder, selected_filename)

    def set_vocal(self, selected_filename):
        if self.current_folder and selected_filename:
            if selected_filename == self.instrumental_selection_name:
                self.instrumental_selection_name = None
                self.instrumental_path = None

            self.vocal_selection_name = selected_filename
            self.vocal_path = os.path.join(self.current_folder, selected_filename)
