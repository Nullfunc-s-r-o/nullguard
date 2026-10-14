// Copyright (C) 2026 Nullfunc s.r.o.
//
// This program is free software: you can redistribute it and/or modify
// it under the terms of the GNU Affero General Public License as published
// by the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.
//
// This program is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU Affero General Public License for more details.
//
// You should have received a copy of the GNU Affero General Public License
// along with this program.  If not, see <https://www.gnu.org/licenses/>.

#pragma once
#include <string>
#include <fstream>
#include <vector>
#include <regex>

class LogWatcher {
private:
	std::string filePath;
	std::ifstream fileStream; // Input file stream to read the log file
	std::streampos lastReadPosition; // Position in the file where the last read ended
	std::regex filterRegex; // Regex to filter log lines

public:
	// Constructor initializes the watcher with file path, regex pattern, and optional starting position
	LogWatcher(const std::string& path, const std::string& pattern, long long initialPos = 0);
	~LogWatcher(); // Destructor

	std::vector<std::string> poll(); // Method to poll the log file for new matching entries
	
	// Get the current read position for persistence
	long long get_position() const;
};