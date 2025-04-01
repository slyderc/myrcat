#!/bin/bash
# Initialize or upgrade Myrcat database with the current schema

# Default database location
DB_PATH="myrcat.db"

# Help message
function show_help {
    echo "Usage: $0 [OPTIONS]"
    echo "Initialize or upgrade Myrcat database with the current schema"
    echo ""
    echo "Options:"
    echo "  -d, --database PATH   Specify database path (default: ./myrcat.db)"
    echo "  -b, --backup          Create a backup before making changes"
    echo "  -f, --force           Force reinitialization even if database exists"
    echo "  -h, --help            Show this help message"
    echo ""
}

# Process command line arguments
BACKUP=0
FORCE=0

while [[ $# -gt 0 ]]; do
    key="$1"
    case $key in
        -d|--database)
            DB_PATH="$2"
            shift
            shift
            ;;
        -b|--backup)
            BACKUP=1
            shift
            ;;
        -f|--force)
            FORCE=1
            shift
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# Get the directory of this script
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
SCHEMA_PATH="$SCRIPT_DIR/../schema.sql"

# Check if schema file exists
if [ ! -f "$SCHEMA_PATH" ]; then
    echo "Error: Schema file not found at: $SCHEMA_PATH"
    exit 1
fi

# Check if database already exists
if [ -f "$DB_PATH" ] && [ $FORCE -eq 0 ]; then
    echo "Database file already exists: $DB_PATH"
    read -p "Do you want to apply schema changes to this database? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Operation cancelled."
        exit 0
    fi
fi

# Create backup if requested
if [ $BACKUP -eq 1 ] && [ -f "$DB_PATH" ]; then
    BACKUP_PATH="${DB_PATH}.$(date +%Y%m%d%H%M%S).bak"
    echo "Creating backup: $BACKUP_PATH"
    cp "$DB_PATH" "$BACKUP_PATH"
    if [ $? -ne 0 ]; then
        echo "Error: Failed to create backup"
        exit 1
    fi
fi

# Apply schema
echo "Applying schema to database: $DB_PATH"
cat "$SCHEMA_PATH" | sqlite3 "$DB_PATH"

if [ $? -eq 0 ]; then
    echo "✅ Database schema successfully applied"
    
    # Verify database
    echo "Verifying tables..."
    TABLE_COUNT=$(sqlite3 "$DB_PATH" "SELECT count(*) FROM sqlite_master WHERE type='table'")
    echo "Found $TABLE_COUNT tables in database"
    
    # Show version
    DB_VERSION=$(sqlite3 "$DB_PATH" "SELECT version FROM db_version WHERE id=1")
    echo "Database schema version: $DB_VERSION"
    
    echo "Done."
    exit 0
else
    echo "❌ Error applying database schema"
    exit 1
fi