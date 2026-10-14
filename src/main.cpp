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
#include "SystemMonitor.h"
#include <pybind11/pybind11.h>
#include <pybind11/stl.h> // Required for automatic conversion of C++ std::vector and std::map to Python list and dict

namespace py = pybind11;

// PYBIND11_MODULE creates the entry point for the Python extension.
// The first argument (nullguard_core) must match the target name in CMakeLists.txt.
PYBIND11_MODULE(nullguard_core, m) {
	m.doc() = "C++ Log Watcher and System Monitor module by Nullfunc";

	// Expose the LogWatcher C++ class to Python
	// py::class_ binds a C++ class or struct
	py::class_<LogWatcher>(m, "LogWatcher")
		// Bind the constructor and specify Python keyword arguments with py::arg()
		.def(py::init<const std::string&, const std::string&, long long>(),
			 py::arg("path"), py::arg("pattern"), py::arg("initialPos") = 0)
		// Bind member functions
		.def("poll", &LogWatcher::poll, "Read the log file and return lines matching the regex")
		.def("get_position", &LogWatcher::get_position, "Get the current file read pointer position");

	// Expose the SystemMonitor C++ class to Python
	py::class_<SystemMonitor>(m, "SystemMonitor")
		.def(py::init<>())
		.def("get_metrics", &SystemMonitor::get_metrics, "Get system metrics (CPU, RAM, Disk, Load Avg, Swap)");
}