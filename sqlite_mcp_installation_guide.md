# SQLite MCP Installation Guide

## Prerequisites
- Windows 10 or later
- Python 3.9 or later
- Git installed
- Node.js and npm (for UV)

## 1. Install SQLite

### Windows Installation
1. Download SQLite from the official website:
   - Visit [SQLite Download Page](https://www.sqlite.org/download.html)
   - Download `sqlite-tools-win32-x86-*.zip` (Windows command-line tools)
   - Download `sqlite-dll-win64-x64-*.zip` (Windows DLL)

2. Create SQLite directory:
   ```powershell
   mkdir C:\sqlite
   ```

3. Extract both downloaded files to `C:\sqlite`

4. Add SQLite to PATH:
   - Open System Properties > Advanced > Environment Variables
   - Under System Variables, find PATH
   - Add `C:\sqlite` to PATH

5. Verify installation:
   ```powershell
   sqlite3 --version
   ```

## 2. Set Up MCP Environment

1. Clone the MCP repository:
   ```powershell
   git clone https://github.com/your-org/mcp-project.git
   cd mcp-project
   ```

2. Create and activate virtual environment:
   ```powershell
   python -m venv venv
   .\venv\Scripts\activate
   ```

3. Install required packages:
   ```powershell
   pip install flask python-dotenv sqlite3
   ```

## 3. Configure MCP for SQLite

1. Create `.env` file:
   ```
   DB_PATH=./data/mcp.db
   SQLITE_TIMEOUT=30
   SQLITE_JOURNAL_MODE=WAL
   ```

2. Create database directory:
   ```powershell
   mkdir data
   ```

## 4. Install UV (Universal Viewer)

1. Install UV globally:
   ```powershell
   npm install -g @uvjs/uv
   ```

2. Configure UV for SQLite:
   ```powershell
   uv config set sqlite.path C:\sqlite\sqlite3.exe
   ```

## 5. Database Setup

1. Initialize the database:
   ```sql
   CREATE TABLE IF NOT EXISTS mcp_data (
       id INTEGER PRIMARY KEY AUTOINCREMENT,
       name TEXT NOT NULL,
       value TEXT,
       created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
   );
   ```

2. Create indexes:
   ```sql
   CREATE INDEX IF NOT EXISTS idx_mcp_data_name ON mcp_data(name);
   CREATE INDEX IF NOT EXISTS idx_mcp_data_created_at ON mcp_data(created_at);
   ```

## 6. Basic Usage

1. Start MCP server:
   ```powershell
   python app.py
   ```

2. Connect to database:
   ```powershell
   sqlite3 ./data/mcp.db
   ```

3. View data with UV:
   ```powershell
   uv open ./data/mcp.db
   ```

## 7. Best Practices

1. Database Optimization:
   ```sql
   PRAGMA journal_mode=WAL;
   PRAGMA synchronous=NORMAL;
   PRAGMA temp_store=MEMORY;
   PRAGMA mmap_size=30000000000;
   ```

2. Regular Maintenance:
   ```sql
   VACUUM;
   ANALYZE;
   ```

3. Backup Strategy:
   ```powershell
   sqlite3 ./data/mcp.db ".backup './backup/mcp_backup.db'"
   ```

## 8. Troubleshooting

### Common Issues:

1. Database Locked:
   - Ensure all connections are properly closed
   - Check for running processes using:
     ```powershell
     Get-Process | Where-Object {$_.Name -like "*sqlite*"}
     ```

2. Permission Issues:
   - Verify file permissions:
     ```powershell
     icacls ./data/mcp.db
     ```
   - Grant necessary permissions:
     ```powershell
     icacls ./data/mcp.db /grant Users:F
     ```

3. Performance Issues:
   - Run ANALYZE to update statistics
   - Check and optimize indexes
   - Monitor disk I/O

## 9. Security Considerations

1. File Permissions:
   - Restrict access to database file
   - Use appropriate file system permissions

2. Connection Security:
   - Use parameterized queries
   - Implement proper authentication
   - Regular security audits

## 10. Updating and Maintenance

1. Regular Updates:
   ```powershell
   pip install --upgrade mcp-tools
   npm update -g @uvjs/uv
   ```

2. Database Maintenance:
   ```sql
   PRAGMA integrity_check;
   PRAGMA foreign_key_check;
   ```

## Support and Resources

- [SQLite Documentation](https://www.sqlite.org/docs.html)
- [MCP GitHub Repository](https://github.com/your-org/mcp-project)
- [UV Documentation](https://github.com/uvjs/uv)

## License
This guide is provided under the MIT License. 