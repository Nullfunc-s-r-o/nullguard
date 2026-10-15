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
#include <map>
#include <string>
#include <filesystem>

class SystemMonitor {
public:
    SystemMonitor();
    std::map<std::string, double> get_metrics();
private:
    unsigned long long previousTotalTicks;
    unsigned long long previousIdleTicks;

    double calculate_cpu_usage();
    double calculate_ram_usage();
    void calculate_disk_usage(double& total_gb, double& used_percent);
    void calculate_load_average(double& load1, double& load5, double& load15);
    double calculate_swap_usage();
    void calculate_process_metrics(double& total_processes, double& zombie_processes);
};
