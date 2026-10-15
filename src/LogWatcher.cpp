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

#include "LogWatcher.h"
#include <iostream>
#include <string>
#include <filesystem>

namespace fs = std::filesystem;

LogWatcher::LogWatcher(const std::string& path, const std::string& pattern, long long initialPos) 
	: filePath(path) {
	if (pattern.rfind("(?i)", 0) == 0) {
		filterRegex = std::regex(pattern.substr(4), std::regex_constants::ECMAScript | std::regex_constants::icase);
	} else {
		filterRegex = std::regex(pattern);
	}
	
	fileStream.open(filePath, std::ios::binary);

	if (fileStream.is_open()) {
		if (initialPos > 0) {
			fileStream.seekg(initialPos);
			lastReadPosition = fileStream.tellg();
		} else {
			fileStream.seekg(0, std::ios::end);
			lastReadPosition = fileStream.tellg();
		}

		std::cout << "[OK] Start watching file: " << filePath << '\n';
	}
	else {
		std::cerr << "[ERROR] Cannot open file : " << filePath << '\n';
	}
}

LogWatcher::~LogWatcher() {
	if (fileStream.is_open()) {
		fileStream.close();
		std::cout << "[OK] Stopped watching file." << std::endl;
	}
}

std::vector<std::string> LogWatcher::poll() {
	std::vector<std::string> events;

	if (!fs::exists(filePath)) return events;
	if (!fileStream.is_open()) return events;

	std::uintmax_t currentSize = fs::file_size(filePath);

	if (currentSize == lastReadPosition) {
		return events;
	}

	if (currentSize < lastReadPosition) {
		std::cout << "[INFO] Log rotation detected. Resetting pointer." << '\n';
		lastReadPosition = 0;

		fileStream.close();
		fileStream.open(filePath, std::ios::binary);
	}

	fileStream.clear();
	fileStream.seekg(lastReadPosition);

	std::string line{};

	while (std::getline(fileStream, line)) {
		if (std::regex_search(line, filterRegex)) {
			events.push_back(line);
		}
	}

	fileStream.clear();
	lastReadPosition = fileStream.tellg();

	return events;
}

long long LogWatcher::get_position() const {
	return static_cast<long long>(lastReadPosition);
}