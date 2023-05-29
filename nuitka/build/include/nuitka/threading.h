//     Copyright 2023, Kay Hayen, mailto:kay.hayen@gmail.com
//
//     Part of "Nuitka", an optimizing Python compiler that is compatible and
//     integrates with CPython, but also works on its own.
//
//     Licensed under the Apache License, Version 2.0 (the "License");
//     you may not use this file except in compliance with the License.
//     You may obtain a copy of the License at
//
//        http://www.apache.org/licenses/LICENSE-2.0
//
//     Unless required by applicable law or agreed to in writing, software
//     distributed under the License is distributed on an "AS IS" BASIS,
//     WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
//     See the License for the specific language governing permissions and
//     limitations under the License.
//
#ifndef __NUITKA_THREADING_H__
#define __NUITKA_THREADING_H__

#if PYTHON_VERSION < 0x300
// We share this with CPython bytecode main loop.
PyAPI_DATA(volatile int) _Py_Ticker;
#else
extern volatile int _Py_Ticker;
#define _Py_CheckInterval 20
#endif

#ifdef NUITKA_USE_PYCORE_THREAD_STATE

#if PYTHON_VERSION < 0x380
// Signals pending got their own indicator only in 3.8, covered by calls to do before.
#define HAS_WORK_TO_DO(ceval, ceval2) (ceval2->pending.calls_to_do._value)
#else
#define HAS_WORK_TO_DO(ceval, ceval2) (ceval->signals_pending._value || ceval2->pending.calls_to_do._value)
#endif

NUITKA_MAY_BE_UNUSED static inline bool CONSIDER_THREADING(void) {
    PyThreadState *tstate = PyThreadState_GET();

#if PYTHON_VERSION >= 0x390
    _PyRuntimeState *const runtime = tstate->interp->runtime;
#else
    _PyRuntimeState *const runtime = &_PyRuntime;
#endif

    // This was split in 2 parts in 3.9 or higher.
    struct _ceval_runtime_state *ceval = &runtime->ceval;
#if PYTHON_VERSION >= 0x390
    struct _ceval_state *ceval2 = &tstate->interp->ceval;
#else
    struct _ceval_runtime_state *ceval2 = ceval;
#endif

    /* Pending signals or calls to do*/
    if (HAS_WORK_TO_DO(ceval, ceval2)) {
        int res = Py_MakePendingCalls();

        if (unlikely(res < 0 && ERROR_OCCURRED())) {
            return false;
        }
    }

#ifdef PY_NOGIL
    /* load eval breaker */
    uintptr_t b = _Py_atomic_load_uintptr(&tstate->eval_breaker);

    /* GIL drop request */
    if ((b & EVAL_PENDING_SIGNALS) != 0) {
#else
    /* GIL drop request */
    if (ceval2->gil_drop_request._value) {
#endif
        /* Give another thread a chance */
        PyEval_SaveThread();
        PyEval_AcquireThread(tstate);
    }

    if (unlikely(tstate->async_exc != NULL)) {
        PyObject *async_exc = tstate->async_exc;
        tstate->async_exc = NULL;

        Py_INCREF(async_exc);

        RESTORE_ERROR_OCCURRED(async_exc, NULL, NULL);

        return false;
    }

    return true;
}

#else

NUITKA_MAY_BE_UNUSED static inline bool CONSIDER_THREADING(void) {
    // Decrease ticker
    if (--_Py_Ticker < 0) {
        _Py_Ticker = _Py_CheckInterval;

        int res = Py_MakePendingCalls();

        if (unlikely(res < 0 && ERROR_OCCURRED())) {
            return false;
        }

        PyThreadState *tstate = PyThreadState_GET();
        assert(tstate);

        if (PyEval_ThreadsInitialized()) {
            // Release and acquire the GIL, it's very inefficient, because we
            // don't even know if it makes sense to do it. A controlling thread
            // should be used to determine if it's needed at all.
            PyEval_SaveThread();
            PyEval_AcquireThread(tstate);
        }

        if (unlikely(tstate->async_exc != NULL)) {
            PyObject *async_exc = tstate->async_exc;
            tstate->async_exc = NULL;

            Py_INCREF(async_exc);

            RESTORE_ERROR_OCCURRED(async_exc, NULL, NULL);

            return false;
        }
    }

    return true;
}

#endif

#endif
