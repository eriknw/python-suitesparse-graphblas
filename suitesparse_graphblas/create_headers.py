"""
Script to generate suitesparse_graphblas.h, suitesparse_graphblas_no_complex.h, and source.c files.

    - Copy the SuiteSparse header file GraphBLAS.h to the local directory.
    - Run the C preprocessor (cleans it up, but also loses #define values).
    - Parse the processed header file using pycparser.
    - Create the final files with and without complex types.
    - Check #define values for sanity.

The generated files are then used by cffi to bind to SuiteSparse:GraphBLAS.

When running against new versions of SuiteSparse:GraphBLAS, the most likely
things that may need to change are:

    - Update DEFINES, the integer #define constants defined by SuiteSparse.
    - Update CHAR_DEFINES, the char* #defines.
    - Update IGNORE_DEFINES, #defines that the script may mistakingly identity,
      but that we can safely ignore.
    - Update DEPRECATED: deprecated names (including enum fields) to exclude.

Run `python create_headers.py --help` to see more help.

"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import pycparser
from pycparser import c_ast, c_generator, parse_file


def sort_key(string):
    """e.g., sort 'INT8' before 'INT16'"""
    return string.replace("8", "08")


def has_complex(string):
    return "FC32" in string or "FC64" in string


def groupby(index, seq):
    rv = {}
    for item in seq:
        key = item[index]
        if key in rv:
            rv[key].append(item)
        else:
            rv[key] = [item]
    return rv


AUTO = "/* This file is automatically generated */"

DEPRECATED = {
    # enums
    "GxB_IS_HYPER",
    "GrB_SCMP",
    # functions
    "GxB_kron",
    "GxB_Matrix_resize",
    "GxB_Vector_resize",
    # UnaryOp
    "GxB_ABS_BOOL",
    "GxB_ABS_INT8",
    "GxB_ABS_INT16",
    "GxB_ABS_INT32",
    "GxB_ABS_INT64",
    "GxB_ABS_UINT8",
    "GxB_ABS_UINT16",
    "GxB_ABS_UINT32",
    "GxB_ABS_UINT64",
    "GxB_ABS_FP32",
    "GxB_ABS_FP64",
    # Monoids
    "GxB_MIN_INT8_MONOID",
    "GxB_MIN_INT16_MONOID",
    "GxB_MIN_INT32_MONOID",
    "GxB_MIN_INT64_MONOID",
    "GxB_MIN_UINT8_MONOID",
    "GxB_MIN_UINT16_MONOID",
    "GxB_MIN_UINT32_MONOID",
    "GxB_MIN_UINT64_MONOID",
    "GxB_MIN_FP32_MONOID",
    "GxB_MIN_FP64_MONOID",
    "GxB_MAX_INT8_MONOID",
    "GxB_MAX_INT16_MONOID",
    "GxB_MAX_INT32_MONOID",
    "GxB_MAX_INT64_MONOID",
    "GxB_MAX_UINT8_MONOID",
    "GxB_MAX_UINT16_MONOID",
    "GxB_MAX_UINT32_MONOID",
    "GxB_MAX_UINT64_MONOID",
    "GxB_MAX_FP32_MONOID",
    "GxB_MAX_FP64_MONOID",
    "GxB_PLUS_INT8_MONOID",
    "GxB_PLUS_INT16_MONOID",
    "GxB_PLUS_INT32_MONOID",
    "GxB_PLUS_INT64_MONOID",
    "GxB_PLUS_UINT8_MONOID",
    "GxB_PLUS_UINT16_MONOID",
    "GxB_PLUS_UINT32_MONOID",
    "GxB_PLUS_UINT64_MONOID",
    "GxB_PLUS_FP32_MONOID",
    "GxB_PLUS_FP64_MONOID",
    "GxB_TIMES_INT8_MONOID",
    "GxB_TIMES_INT16_MONOID",
    "GxB_TIMES_INT32_MONOID",
    "GxB_TIMES_INT64_MONOID",
    "GxB_TIMES_UINT8_MONOID",
    "GxB_TIMES_UINT16_MONOID",
    "GxB_TIMES_UINT32_MONOID",
    "GxB_TIMES_UINT64_MONOID",
    "GxB_TIMES_FP32_MONOID",
    "GxB_TIMES_FP64_MONOID",
    "GxB_LOR_BOOL_MONOID",
    "GxB_LAND_BOOL_MONOID",
    "GxB_LXOR_BOOL_MONOID",
    "GxB_LXNOR_BOOL_MONOID",
    # "GxB_EQ_BOOL_MONOID",  # XXX: I prefer this name to GrB_LXNOR_MONOID_BOOL
    # Semirings
    "GxB_PLUS_TIMES_INT8",
    "GxB_PLUS_TIMES_INT16",
    "GxB_PLUS_TIMES_INT32",
    "GxB_PLUS_TIMES_INT64",
    "GxB_PLUS_TIMES_UINT8",
    "GxB_PLUS_TIMES_UINT16",
    "GxB_PLUS_TIMES_UINT32",
    "GxB_PLUS_TIMES_UINT64",
    "GxB_PLUS_TIMES_FP32",
    "GxB_PLUS_TIMES_FP64",
    "GxB_PLUS_MIN_INT8",
    "GxB_PLUS_MIN_INT16",
    "GxB_PLUS_MIN_INT32",
    "GxB_PLUS_MIN_INT64",
    "GxB_PLUS_MIN_UINT8",
    "GxB_PLUS_MIN_UINT16",
    "GxB_PLUS_MIN_UINT32",
    "GxB_PLUS_MIN_UINT64",
    "GxB_PLUS_MIN_FP32",
    "GxB_PLUS_MIN_FP64",
    "GxB_MIN_PLUS_INT8",
    "GxB_MIN_PLUS_INT16",
    "GxB_MIN_PLUS_INT32",
    "GxB_MIN_PLUS_INT64",
    "GxB_MIN_PLUS_UINT8",
    "GxB_MIN_PLUS_UINT16",
    "GxB_MIN_PLUS_UINT32",
    "GxB_MIN_PLUS_UINT64",
    "GxB_MIN_PLUS_FP32",
    "GxB_MIN_PLUS_FP64",
    "GxB_MIN_TIMES_INT8",
    "GxB_MIN_TIMES_INT16",
    "GxB_MIN_TIMES_INT32",
    "GxB_MIN_TIMES_INT64",
    "GxB_MIN_TIMES_UINT8",
    "GxB_MIN_TIMES_UINT16",
    "GxB_MIN_TIMES_UINT32",
    "GxB_MIN_TIMES_UINT64",
    "GxB_MIN_TIMES_FP32",
    "GxB_MIN_TIMES_FP64",
    "GxB_MIN_FIRST_INT8",
    "GxB_MIN_FIRST_INT16",
    "GxB_MIN_FIRST_INT32",
    "GxB_MIN_FIRST_INT64",
    "GxB_MIN_FIRST_UINT8",
    "GxB_MIN_FIRST_UINT16",
    "GxB_MIN_FIRST_UINT32",
    "GxB_MIN_FIRST_UINT64",
    "GxB_MIN_FIRST_FP32",
    "GxB_MIN_FIRST_FP64",
    "GxB_MIN_SECOND_INT8",
    "GxB_MIN_SECOND_INT16",
    "GxB_MIN_SECOND_INT32",
    "GxB_MIN_SECOND_INT64",
    "GxB_MIN_SECOND_UINT8",
    "GxB_MIN_SECOND_UINT16",
    "GxB_MIN_SECOND_UINT32",
    "GxB_MIN_SECOND_UINT64",
    "GxB_MIN_SECOND_FP32",
    "GxB_MIN_SECOND_FP64",
    "GxB_MIN_MAX_INT8",
    "GxB_MIN_MAX_INT16",
    "GxB_MIN_MAX_INT32",
    "GxB_MIN_MAX_INT64",
    "GxB_MIN_MAX_UINT8",
    "GxB_MIN_MAX_UINT16",
    "GxB_MIN_MAX_UINT32",
    "GxB_MIN_MAX_UINT64",
    "GxB_MIN_MAX_FP32",
    "GxB_MIN_MAX_FP64",
    "GxB_MAX_PLUS_INT8",
    "GxB_MAX_PLUS_INT16",
    "GxB_MAX_PLUS_INT32",
    "GxB_MAX_PLUS_INT64",
    "GxB_MAX_PLUS_UINT8",
    "GxB_MAX_PLUS_UINT16",
    "GxB_MAX_PLUS_UINT32",
    "GxB_MAX_PLUS_UINT64",
    "GxB_MAX_PLUS_FP32",
    "GxB_MAX_PLUS_FP64",
    "GxB_MAX_TIMES_INT8",
    "GxB_MAX_TIMES_INT16",
    "GxB_MAX_TIMES_INT32",
    "GxB_MAX_TIMES_INT64",
    "GxB_MAX_TIMES_UINT8",
    "GxB_MAX_TIMES_UINT16",
    "GxB_MAX_TIMES_UINT32",
    "GxB_MAX_TIMES_UINT64",
    "GxB_MAX_TIMES_FP32",
    "GxB_MAX_TIMES_FP64",
    "GxB_MAX_FIRST_INT8",
    "GxB_MAX_FIRST_INT16",
    "GxB_MAX_FIRST_INT32",
    "GxB_MAX_FIRST_INT64",
    "GxB_MAX_FIRST_UINT8",
    "GxB_MAX_FIRST_UINT16",
    "GxB_MAX_FIRST_UINT32",
    "GxB_MAX_FIRST_UINT64",
    "GxB_MAX_FIRST_FP32",
    "GxB_MAX_FIRST_FP64",
    "GxB_MAX_SECOND_INT8",
    "GxB_MAX_SECOND_INT16",
    "GxB_MAX_SECOND_INT32",
    "GxB_MAX_SECOND_INT64",
    "GxB_MAX_SECOND_UINT8",
    "GxB_MAX_SECOND_UINT16",
    "GxB_MAX_SECOND_UINT32",
    "GxB_MAX_SECOND_UINT64",
    "GxB_MAX_SECOND_FP32",
    "GxB_MAX_SECOND_FP64",
    "GxB_MAX_MIN_INT8",
    "GxB_MAX_MIN_INT16",
    "GxB_MAX_MIN_INT32",
    "GxB_MAX_MIN_INT64",
    "GxB_MAX_MIN_UINT8",
    "GxB_MAX_MIN_UINT16",
    "GxB_MAX_MIN_UINT32",
    "GxB_MAX_MIN_UINT64",
    "GxB_MAX_MIN_FP32",
    "GxB_MAX_MIN_FP64",
    "GxB_LOR_LAND_BOOL",
    "GxB_LAND_LOR_BOOL",
    "GxB_LXOR_LAND_BOOL",
    # "GxB_EQ_LOR_BOOL",  # XXX: I prefer this name to GrB_LXNOR_LOR_SEMIRING_BOOL
    # Old deprecated (probably already removed)
    "GrB_eWiseMult_Vector_Semiring",
    "GrB_eWiseMult_Vector_Monoid",
    "GrB_eWiseMult_Vector_BinaryOp",
    "GrB_eWiseMult_Matrix_Semiring",
    "GrB_eWiseMult_Matrix_Monoid",
    "GrB_eWiseMult_Matrix_BinaryOp",
    "GrB_eWiseAdd_Vector_Semiring",
    "GrB_eWiseAdd_Vector_Monoid",
    "GrB_eWiseAdd_Vector_BinaryOp",
    "GrB_eWiseAdd_Matrix_Semiring",
    "GrB_eWiseAdd_Matrix_Monoid",
    "GrB_eWiseAdd_Matrix_BinaryOp",
}

DEFINES = {
    "GxB_STDC_VERSION",
    "GxB_IMPLEMENTATION_MAJOR",
    "GxB_IMPLEMENTATION_MINOR",
    "GxB_IMPLEMENTATION_SUB",
    "GxB_SPEC_MAJOR",
    "GxB_SPEC_MINOR",
    "GxB_SPEC_SUB",
    "GxB_IMPLEMENTATION",
    "GxB_SPEC_VERSION",
    "GxB_INDEX_MAX",
    "GRB_VERSION",
    "GRB_SUBVERSION",
    "GxB_NTHREADS",
    "GxB_CHUNK",
    "GxB_GPU_CONTROL",
    "GxB_GPU_CHUNK",
    "GxB_HYPERSPARSE",
    "GxB_SPARSE",
    "GxB_BITMAP",
    "GxB_FULL",
    "GxB_NBITMAP_SWITCH",
    "GxB_ANY_SPARSITY",
    "GxB_AUTO_SPARSITY",
    "GxB_RANGE",
    "GxB_STRIDE",
    "GxB_BACKWARDS",
    "GxB_BEGIN",
    "GxB_END",
    "GxB_INC",
}

CHAR_DEFINES = {
    "GxB_IMPLEMENTATION_NAME",
    "GxB_IMPLEMENTATION_DATE",
    "GxB_SPEC_DATE",
    "GxB_IMPLEMENTATION_ABOUT",
    "GxB_IMPLEMENTATION_LICENSE",
    "GxB_SPEC_ABOUT",
}

IGNORE_DEFINES = {
    "CMPLX",
    "CMPLXF",
    "GB_PUBLIC",
    "GRAPHBLAS_H",
    "GrB_INVALID_HANDLE",
    "GrB_NULL",
    "GxB_SUITESPARSE_GRAPHBLAS",
    "NMACRO",
    # deprecated
    "GxB_HYPER",
}


class VisitEnumTypedef(c_generator.CGenerator):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.results = []

    def visit_Typedef(self, node):
        rv = super().visit_Typedef(node)
        if isinstance(node.type.type, c_ast.Enum):
            self.results.append(rv + ";")
        return rv


def get_ast(filename):
    fake_include = os.path.dirname(pycparser.__file__) + "utils/fake_libc_include"
    ast = parse_file(filename, cpp_args=f"-I{fake_include}")
    return ast


def get_groups(ast):
    generator = c_generator.CGenerator()
    lines = generator.visit(ast).splitlines()

    seen = set()
    groups = {}
    vals = {x for x in lines if "extern GrB_Info GxB" in x} - seen
    seen.update(vals)
    groups["GxB methods"] = sorted(vals, key=sort_key)

    vals = {x for x in lines if "extern GrB_Info GrB" in x} - seen
    seen.update(vals)
    groups["GrB methods"] = sorted(vals, key=sort_key)

    vals = {x for x in lines if "extern GrB_Info GB" in x} - seen
    seen.update(vals)
    groups["GB methods"] = sorted(vals, key=sort_key)

    missing_methods = {x for x in lines if "extern GrB_Info " in x} - seen
    assert not missing_methods

    vals = {x for x in lines if "extern GrB" in x} - seen
    seen.update(vals)
    groups["GrB objects"] = sorted(vals, key=sort_key)

    vals = {x for x in lines if "extern GxB" in x} - seen
    seen.update(vals)
    groups["GxB objects"] = sorted(vals, key=sort_key)

    vals = {x for x in lines if "extern const" in x and "GxB" in x} - seen
    seen.update(vals)
    groups["GxB const"] = sorted(vals, key=sort_key)

    vals = {x for x in lines if "extern const" in x and "GrB" in x} - seen
    seen.update(vals)
    groups["GrB const"] = sorted(vals, key=sort_key)

    missing_const = {x for x in lines if "extern const" in x} - seen
    assert not missing_const

    vals = {x for x in lines if "typedef" in x and "GxB" in x and "(" not in x} - seen
    seen.update(vals)
    groups["GxB typedef"] = sorted(vals, key=sort_key)

    vals = {x for x in lines if "typedef" in x and "GrB" in x and "(" not in x} - seen
    seen.update(vals)
    groups["GrB typedef"] = sorted(vals, key=sort_key)

    missing_typedefs = {x for x in lines if "typedef" in x and "GB" in x and "(" not in x} - seen
    assert not missing_typedefs
    assert all(x.endswith(";") for x in seen)  # sanity check

    g = VisitEnumTypedef()
    _ = g.visit(ast)
    enums = g.results

    vals = {x for x in enums if "} GrB" in x}
    for val in vals:
        seen.update(val.splitlines())
    groups["GrB typedef enums"] = sorted(vals, key=lambda x: sort_key(x.rsplit("}", 1)[-1]))

    vals = {x for x in enums if "} GxB" in x}
    for val in vals:
        seen.update(val.splitlines())
    groups["GxB typedef enums"] = sorted(vals, key=lambda x: sort_key(x.rsplit("}", 1)[-1]))

    missing_enums = set(enums) - set(groups["GrB typedef enums"]) - set(groups["GxB typedef enums"])
    assert not missing_enums

    vals = {x for x in lines if "typedef" in x and "GxB" in x} - seen
    seen.update(vals)
    groups["GxB typedef funcs"] = sorted(vals, key=sort_key)

    vals = {x for x in lines if "typedef" in x and "GrB" in x} - seen
    assert not vals
    groups["not seen"] = sorted(set(lines) - seen, key=sort_key)
    for group in groups["not seen"]:
        assert "extern" not in group, group
    return groups


def get_group_info(groups, ast, *, skip_complex=False):
    rv = {}

    def handle_constants(group):
        for line in group:
            extern, const, ctype, name = line.split(" ")
            assert name.endswith(";")
            name = name[:-1].replace("(void)", "()")
            assert extern == "extern"
            assert const == "const"
            if name in DEPRECATED:
                continue
            if skip_complex and has_complex(line):
                continue
            info = {
                "text": line,
            }
            yield info

    rv["GrB const"] = list(handle_constants(groups["GrB const"]))
    rv["GxB const"] = list(handle_constants(groups["GxB const"]))

    def handle_objects(group):
        for line in group:
            extern, ctype, name = line.split(" ")
            assert name.endswith(";")
            name = name[:-1]
            assert extern == "extern"
            if name in DEPRECATED:
                continue
            if skip_complex and has_complex(line):
                continue
            info = {
                "text": line,
            }
            yield info

    rv["GrB objects"] = list(handle_objects(groups["GrB objects"]))
    rv["GxB objects"] = list(handle_objects(groups["GxB objects"]))

    def handle_enums(group):
        for text in group:
            text = text.replace("enum \n", "enum\n")
            typedef, bracket, *fields, name = text.splitlines()
            assert typedef.strip() == "typedef enum"
            assert bracket == "{"
            assert name.startswith("}")
            assert name.endswith(";")
            name = name[1:-1].strip()
            if name in DEPRECATED:
                continue
            if skip_complex and has_complex(name):
                continue

            # Break this open so we can remove unwanted deprecated fields.
            # Instead of traversing the AST, munging string is good enough.
            typedef, bracket, *fields, cname = text.splitlines()
            typedef = typedef.strip()
            assert typedef.strip() == "typedef enum"
            assert bracket == "{"
            assert cname.startswith("}")
            assert cname.endswith(";")
            new_fields = []
            for field in fields:
                if field.endswith(","):
                    field = field[:-1]
                field = field.strip()
                cfieldname, eq, val = field.split(" ")
                assert eq == "="
                if cfieldname in DEPRECATED:
                    continue
                if skip_complex and has_complex(cfieldname):
                    continue
                new_fields.append(field)
            if not new_fields:
                continue
            lines = [typedef, bracket]
            for field in new_fields:
                lines.append(f"  {field},")
            lines[-1] = lines[-1][:-1]  # remove last comma
            lines.append(cname)
            info = {
                "orig_text": text,
                "text": "\n".join(lines),
            }
            yield info

    rv["GrB typedef enums"] = list(handle_enums(groups["GrB typedef enums"]))
    rv["GxB typedef enums"] = list(handle_enums(groups["GxB typedef enums"]))

    def handle_typedefs(group):
        for line in group:
            typedef, *ctypes, name = line.split(" ")
            assert typedef == "typedef"
            assert name.endswith(";")
            name = name[:-1]
            if name in DEPRECATED:
                continue
            if skip_complex and has_complex(line):
                continue
            info = {
                "text": line,
            }
            yield info

    rv["GrB typedef"] = list(handle_typedefs(groups["GrB typedef"]))
    rv["GxB typedef"] = list(handle_typedefs(groups["GxB typedef"]))

    def handle_typedef_funcs(group):
        for line in group:
            assert line.endswith(";") and line.startswith("typedef")
            if skip_complex and has_complex(line):
                continue
            info = {
                "text": line,
            }
            yield info

    rv["GxB typedef funcs"] = list(handle_typedef_funcs(groups["GxB typedef funcs"]))

    class FuncDeclVisitor(c_ast.NodeVisitor):
        def __init__(self):
            self.functions = []

        def visit_Decl(self, node):
            if isinstance(node.type, c_ast.FuncDecl) and node.storage == ["extern"]:
                self.functions.append(node)

    def handle_function_node(node):
        if generator.visit(node.type.type) != "GrB_Info":
            raise ValueError(generator.visit(node))
        if node.name in DEPRECATED:
            return
        text = generator.visit(node)
        text += ";"
        if skip_complex and has_complex(text):
            return
        if "GrB_Matrix" in text:
            group = "matrix"
        elif "GrB_Vector" in text:
            group = "vector"
        elif "GxB_Scalar" in text:
            group = "scalar"
        else:
            group = node.name.split("_", 2)[1]
            group = {
                # Apply our naming scheme
                "GrB_Matrix": "matrix",
                "GrB_Vector": "vector",
                "GxB_Scalar": "scalar",
                "SelectOp": "selectop",
                "BinaryOp": "binary",
                "Desc": "descriptor",
                "Descriptor": "descriptor",
                "Monoid": "monoid",
                "Semiring": "semiring",
                "Type": "type",
                "UnaryOp": "unary",
                # "everything else" is "core"
                "getVersion": "core",
                "Global": "core",
                "cuda": "core",
                "finalize": "core",
                "init": "core",
                "wait": "core",
            }[group]
        return {
            "name": node.name,
            "group": group,
            "node": node,
            "text": text,
        }

    generator = c_generator.CGenerator()
    visitor = FuncDeclVisitor()
    visitor.visit(ast)
    grb_nodes = [node for node in visitor.functions if node.name.startswith("GrB_")]
    gxb_nodes = [node for node in visitor.functions if node.name.startswith("GxB_")]
    gb_nodes = [node for node in visitor.functions if node.name.startswith("GB_")]
    assert len(grb_nodes) == len(groups["GrB methods"])
    assert len(gxb_nodes) == len(groups["GxB methods"])
    assert len(gb_nodes) == len(groups["GB methods"])

    grb_funcs = (handle_function_node(node) for node in grb_nodes)
    gxb_funcs = (handle_function_node(node) for node in gxb_nodes)
    gb_funcs = (handle_function_node(node) for node in gb_nodes)
    grb_funcs = [x for x in grb_funcs if x is not None]
    gxb_funcs = [x for x in gxb_funcs if x is not None]
    gb_funcs = [x for x in gb_funcs if x is not None]

    rv["GrB methods"] = sorted(grb_funcs, key=lambda x: sort_key(x["text"]))
    rv["GxB methods"] = sorted(gxb_funcs, key=lambda x: sort_key(x["text"]))
    rv["GB methods"] = sorted(gb_funcs, key=lambda x: sort_key(x["text"]))
    for key in groups.keys() - rv.keys():
        rv[key] = groups[key]
    return rv


def parse_header(filename, *, skip_complex=False):
    ast = get_ast(filename)
    groups = get_groups(ast)
    return get_group_info(groups, ast, skip_complex=skip_complex)


def create_header_text(groups, *, char_defines=None, defines=None):
    if char_defines is None:
        char_defines = CHAR_DEFINES
    if defines is None:
        defines = DEFINES

    text = [AUTO]
    text.append("/* GrB typedefs */")
    for group in groups["GrB typedef"]:
        text.append(group["text"])
    text.append("")
    text.append("/* GxB typedefs */")
    for group in groups["GxB typedef"]:
        text.append(group["text"])
    text.append("")
    text.append("/* GxB typedefs (functions) */")
    for group in groups["GxB typedef funcs"]:
        text.append(group["text"])
    text.append("")
    text.append("/* GrB enums */")
    for group in groups["GrB typedef enums"]:
        text.append(group["text"])
        text.append("")
    text.append("/* GxB enums */")
    for group in groups["GxB typedef enums"]:
        text.append(group["text"])
        text.append("")
    text.append("/* GrB consts */")
    for group in groups["GrB const"]:
        text.append(group["text"])
    text.append("")
    text.append("/* GxB consts */")
    for group in groups["GxB const"]:
        text.append(group["text"])
    text.append("")
    text.append("/* GrB objects */")
    for group in groups["GrB objects"]:
        if "GxB" not in group["text"]:
            text.append(group["text"])
    text.append("")
    text.append("/* GrB objects (extended) */")
    for group in groups["GrB objects"]:
        if "GxB" in group["text"]:
            text.append(group["text"])
    text.append("")
    text.append("/* GxB objects */")
    for group in groups["GxB objects"]:
        text.append(group["text"])

    def handle_funcs(group):
        groups = groupby("group", group)
        for name in sorted(groups, key=sort_key):
            yield ""
            yield f"/* {name} */"
            for info in groups[name]:
                yield info["text"]

    text.append("")
    text.append("/****************")
    text.append("* GrB functions *")
    text.append("****************/")
    text.extend(handle_funcs(groups["GrB methods"]))

    text.append("")
    text.append("/***************")
    text.append("* GB functions *")
    text.append("***************/")
    text.extend(handle_funcs(groups["GB methods"]))

    text.append("")
    text.append("/****************")
    text.append("* GxB functions *")
    text.append("****************/")
    text.extend(handle_funcs(groups["GxB methods"]))

    text.append("")
    text.append("/* int DEFINES */")
    for item in sorted(defines, key=sort_key):
        text.append(f"#define {item} ...")

    text.append("")
    text.append("/* char* DEFINES */")
    for item in sorted(char_defines, key=sort_key):
        text.append(f"extern char *{item}_STR;")
    return text


def create_source_text(*, char_defines=None):
    if char_defines is None:
        char_defines = CHAR_DEFINES
    text = [
        AUTO,
        '#include "GraphBLAS.h"',
    ]
    for item in sorted(char_defines, key=sort_key):
        text.append(f"char *{item}_STR = {item};")
    return text


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--graphblas",
        help="Path to GraphBLAS.h of SuiteSparse.  Default will look in Python prefix path.",
        default=os.path.join(sys.prefix, "include", "GraphBLAS.h"),
    )
    parser.add_argument(
        "--show-skipped",
        action="store_true",
        help="If specified, then print the lines that were skipped when parsing the header file.",
    )
    args = parser.parse_args()

    thisdir = os.path.dirname(__file__)
    # copy the original to this file
    graphblas_h = os.path.join(thisdir, "GraphBLAS-orig.h")
    # after the preprocessor
    processed_h = os.path.join(thisdir, "GraphBLAS-processed.h")

    # final files used by cffi (with and without complex numbers)
    final_h = os.path.join(thisdir, "suitesparse_graphblas.h")
    final_no_complex_h = os.path.join(thisdir, "suitesparse_graphblas_no_complex.h")
    source_c = os.path.join(thisdir, "source.c")

    # Copy original file
    print(f"Step 1: copy {args.graphblas} to {graphblas_h}")
    if not os.path.exists(args.graphblas):
        raise FileNotFoundError(f"File not found: {args.graphblas}")
    shutil.copyfile(args.graphblas, graphblas_h)

    # Run it through the preprocessor
    print(f"Step 2: run preprocessor to create {processed_h}")
    include = os.path.join(os.path.dirname(pycparser.__file__), "utils", "fake_libc_include")
    command = (
        f"gcc -nostdinc -E -I{include} {graphblas_h} "
        f"| sed 's/ complex / _Complex /g' > {processed_h}"
    )
    res = subprocess.run(command, shell=True)
    if res.returncode != 0:
        raise RuntimeError("Subprocess command failed", res)

    # Create final header file
    print(f"Step 3: parse header file to create {final_h}")
    groups = parse_header(processed_h, skip_complex=False)
    text = create_header_text(groups)
    with open(final_h, "w") as f:
        f.write("\n".join(text))

    # Create final header file (no complex)
    print(f"Step 4: parse header file to create {final_no_complex_h}")
    groups_no_complex = parse_header(processed_h, skip_complex=True)
    text = create_header_text(groups_no_complex)
    with open(final_no_complex_h, "w") as f:
        f.write("\n".join(text))

    # Create source
    print(f"Step 5: create {source_c}")
    text = create_source_text()
    with open(source_c, "w") as f:
        f.write("\n".join(text))

    # Check defines
    print("Step 6: check #define definitions")
    with open(graphblas_h) as f:
        text = f.read()
    define_pattern = re.compile(r"#define\s+\w+\s+")
    defines = {x[len("#define") :].strip() for x in define_pattern.findall(text)}
    extra_defines = (DEFINES | CHAR_DEFINES) - defines
    if extra_defines:
        # Should this raise?  If it's a problem, it will raise when compiling.
        print(
            f"WARNING: the following #define values weren't found in {graphblas_h}: "
            + ", ".join(sorted(extra_defines))
        )
    unknown_defines = defines - DEFINES - CHAR_DEFINES - IGNORE_DEFINES
    if unknown_defines:
        raise ValueError(
            f"Unknown #define values found in {graphblas_h}: " + ", ".join(sorted(unknown_defines))
        )
    print("Success!", "\N{ROCKET}")
    if args.show_skipped:
        print()
        print(f"Showing lines from {processed_h} that were skipped when creating {final_h}:")
        print("-" * 80)
        for line in sorted(groups["not seen"], key=sort_key):
            print(line)


if __name__ == "__main__":
    main()
