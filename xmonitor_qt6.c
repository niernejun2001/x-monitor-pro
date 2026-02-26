#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

int main(int argc, char *argv[]) {
    char exe_path[PATH_MAX];
    ssize_t len = readlink("/proc/self/exe", exe_path, sizeof(exe_path) - 1);
    if (len < 0) {
        perror("readlink");
        return 1;
    }
    exe_path[len] = '\0';

    char *slash = strrchr(exe_path, '/');
    if (!slash) {
        fprintf(stderr, "failed to resolve launcher directory\n");
        return 1;
    }
    *slash = '\0';

    char python_path[PATH_MAX];
    char script_path[PATH_MAX];
    if (snprintf(python_path, sizeof(python_path), "%s/venv/bin/python", exe_path) >= (int)sizeof(python_path)) {
        fprintf(stderr, "python path too long\n");
        return 1;
    }
    if (snprintf(script_path, sizeof(script_path), "%s/start_qt6.py", exe_path) >= (int)sizeof(script_path)) {
        fprintf(stderr, "script path too long\n");
        return 1;
    }

    char **new_argv = calloc((size_t)argc + 2, sizeof(char *));
    if (!new_argv) {
        perror("calloc");
        return 1;
    }

    new_argv[0] = python_path;
    new_argv[1] = script_path;
    for (int i = 1; i < argc; i++) {
        new_argv[i + 1] = argv[i];
    }
    new_argv[argc + 1] = NULL;

    execv(python_path, new_argv);
    perror("execv");
    free(new_argv);
    return 1;
}
