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

#include "SystemMonitor.h"
#include <fstream>
#include <sstream>
#include <iostream>
#include <filesystem>
#include <algorithm>

#ifdef _WIN32
#include <windows.h>
#else
#include <stdlib.h> // for getloadavg
#endif

SystemMonitor::SystemMonitor() : previousTotalTicks(0), previousIdleTicks(0) {
    // Initial call to populate previous ticks for delta calculation
    calculate_cpu_usage();
}

std::map<std::string, double> SystemMonitor::get_metrics() {
    double disk_total = 0.0, disk_used_pct = 0.0;
    calculate_disk_usage(disk_total, disk_used_pct);

    double load1 = 0.0, load5 = 0.0, load15 = 0.0;
    calculate_load_average(load1, load5, load15);

    double total_procs = 0.0, zombie_procs = 0.0;
    calculate_process_metrics(total_procs, zombie_procs);

    return {
        {"cpu_usage_percent", calculate_cpu_usage()},
        {"ram_usage_percent", calculate_ram_usage()},
        {"disk_total_gb", disk_total},
        {"disk_used_percent", disk_used_pct},
        {"load_1m", load1},
        {"load_5m", load5},
        {"load_15m", load15},
        {"swap_used_percent", calculate_swap_usage()},
        {"total_processes", total_procs},
        {"zombie_processes", zombie_procs}
    };
}

double SystemMonitor::calculate_cpu_usage() {
#ifdef _WIN32
    FILETIME idleTime, kernelTime, userTime;
    if (GetSystemTimes(&idleTime, &kernelTime, &userTime)) {
        auto to_ull = [](const FILETIME& ft) {
            return (static_cast<unsigned long long>(ft.dwHighDateTime) << 32) | ft.dwLowDateTime;
        };
        unsigned long long idle = to_ull(idleTime);
        unsigned long long sys = to_ull(kernelTime);
        unsigned long long user = to_ull(userTime);

        unsigned long long currentTotal = sys + user;
        unsigned long long currentIdle = idle;
        
        double cpu = 0.0;
        if (previousTotalTicks > 0) {
            unsigned long long totalDiff = currentTotal - previousTotalTicks;
            unsigned long long idleDiff = currentIdle - previousIdleTicks;
            if (totalDiff > 0) {
                cpu = (totalDiff - idleDiff) * 100.0 / totalDiff;
            }
        }
        previousTotalTicks = currentTotal;
        previousIdleTicks = currentIdle;
        return cpu;
    }
    return 0.0;
#else
    std::ifstream stat_file("/proc/stat");
    if (!stat_file.is_open()) return 0.0;

    std::string line;
    std::getline(stat_file, line);
    std::istringstream iss(line);
    std::string cpu_label;
    iss >> cpu_label;

    unsigned long long user, nice, system, idle, iowait, irq, softirq, steal, guest, guest_nice;
    iss >> user >> nice >> system >> idle >> iowait >> irq >> softirq >> steal >> guest >> guest_nice;

    unsigned long long currentIdle = idle + iowait;
    unsigned long long currentNonIdle = user + nice + system + irq + softirq + steal;
    unsigned long long currentTotal = currentIdle + currentNonIdle;

    double cpu = 0.0;
    if (previousTotalTicks > 0) {
        unsigned long long totalDiff = currentTotal - previousTotalTicks;
        unsigned long long idleDiff = currentIdle - previousIdleTicks;
        if (totalDiff > 0) {
            cpu = (static_cast<double>(totalDiff) - static_cast<double>(idleDiff)) * 100.0 / static_cast<double>(totalDiff);
        }
    }
    previousTotalTicks = currentTotal;
    previousIdleTicks = currentIdle;
    return cpu;
#endif
}

double SystemMonitor::calculate_ram_usage() {
#ifdef _WIN32
    MEMORYSTATUSEX memInfo;
    memInfo.dwLength = sizeof(MEMORYSTATUSEX);
    if (GlobalMemoryStatusEx(&memInfo)) {
        return (memInfo.ullTotalPhys - memInfo.ullAvailPhys) * 100.0 / memInfo.ullTotalPhys;
    }
    return 0.0;
#else
    std::ifstream meminfo("/proc/meminfo");
    if (!meminfo.is_open()) return 0.0;

    std::string line;
    unsigned long long total_mem = 0, available_mem = 0;
    while (std::getline(meminfo, line)) {
        if (line.find("MemTotal:") == 0) {
            std::istringstream iss(line.substr(9));
            iss >> total_mem;
        } else if (line.find("MemAvailable:") == 0) {
            std::istringstream iss(line.substr(13));
            iss >> available_mem;
        }
    }
    if (total_mem > 0) {
        return (static_cast<double>(total_mem) - static_cast<double>(available_mem)) * 100.0 / static_cast<double>(total_mem);
    }
    return 0.0;
#endif
}

void SystemMonitor::calculate_disk_usage(double& total_gb, double& used_percent) {
    try {
#ifdef _WIN32
        std::filesystem::space_info si = std::filesystem::space("C:\\");
#else
        std::filesystem::space_info si = std::filesystem::space("/");
#endif
        total_gb = static_cast<double>(si.capacity) / (1024.0 * 1024.0 * 1024.0);
        if (si.capacity > 0) {
            used_percent = (static_cast<double>(si.capacity - si.free) / static_cast<double>(si.capacity)) * 100.0;
        } else {
            used_percent = 0.0;
        }
    } catch (const std::filesystem::filesystem_error&) {
        total_gb = 0.0;
        used_percent = 0.0;
    }
}

void SystemMonitor::calculate_load_average(double& load1, double& load5, double& load15) {
#ifdef _WIN32
    load1 = 0.0;
    load5 = 0.0;
    load15 = 0.0;
#else
    double loadavg[3];
    if (getloadavg(loadavg, 3) != -1) {
        load1 = loadavg[0];
        load5 = loadavg[1];
        load15 = loadavg[2];
    } else {
        load1 = 0.0;
        load5 = 0.0;
        load15 = 0.0;
    }
#endif
}

double SystemMonitor::calculate_swap_usage() {
#ifdef _WIN32
    return 0.0; // Fallback for Windows
#else
    std::ifstream meminfo("/proc/meminfo");
    if (!meminfo.is_open()) return 0.0;

    std::string line;
    unsigned long long swap_total = 0, swap_free = 0;
    while (std::getline(meminfo, line)) {
        if (line.find("SwapTotal:") == 0) {
            std::istringstream iss(line.substr(10));
            iss >> swap_total;
        } else if (line.find("SwapFree:") == 0) {
            std::istringstream iss(line.substr(9));
            iss >> swap_free;
        }
    }
    if (swap_total > 0) {
        return (static_cast<double>(swap_total) - static_cast<double>(swap_free)) * 100.0 / static_cast<double>(swap_total);
    }
    return 0.0;
#endif
}

void SystemMonitor::calculate_process_metrics(double& total_processes, double& zombie_processes) {
#ifdef _WIN32
    total_processes = 0.0;
    zombie_processes = 0.0;
#else
    long total = 0;
    long zombies = 0;
    
    try {
        for (const auto& entry : std::filesystem::directory_iterator("/proc")) {
            if (!entry.is_directory()) continue;
            
            std::string filename = entry.path().filename().string();
            bool is_pid = !filename.empty() && std::all_of(filename.begin(), filename.end(), ::isdigit);
            
            if (is_pid) {
                total++;
                std::ifstream stat_file(entry.path() / "stat");
                if (stat_file.is_open()) {
                    std::string line;
                    if (std::getline(stat_file, line)) {
                        size_t rparen = line.find_last_of(')');
                        if (rparen != std::string::npos && rparen + 2 < line.size()) {
                            char state = line[rparen + 2];
                            if (state == 'Z') {
                                zombies++;
                            }
                        }
                    }
                }
            }
        }
    } catch (const std::filesystem::filesystem_error&) {
    }
    
    total_processes = static_cast<double>(total);
    zombie_processes = static_cast<double>(zombies);
#endif
}
