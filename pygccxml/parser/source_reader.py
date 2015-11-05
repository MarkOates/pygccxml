# Copyright 2014-2015 Insight Software Consortium.
# Copyright 2004-2008 Roman Yakovenko.
# Distributed under the Boost Software License, Version 1.0.
# See http://www.boost.org/LICENSE_1_0.txt

import os
import platform
from . import linker
from . import config
from . import patcher
import subprocess
import pygccxml.utils

try:  # select the faster xml parser
    from .etree_scanner import etree_scanner_t as scanner_t
except:
    from .scanner import scanner_t

from . import declarations_cache
from pygccxml import utils
from pygccxml import declarations


def bind_aliases(decls):
    """
    This function binds between class and it's typedefs.

    :param decls: list of all declarations
    :type all_classes: list of :class:`declarations.declaration_t` items

    :rtype: None

    """

    visited = set()
    typedefs = [
        decl for decl in decls if isinstance(decl, declarations.typedef_t)]
    for decl in typedefs:
        type_ = declarations.remove_alias(decl.type)
        if not isinstance(type_, declarations.declarated_t):
            continue
        cls_inst = type_.declaration
        if not isinstance(cls_inst, declarations.class_types):
            continue
        if id(cls_inst) not in visited:
            visited.add(id(cls_inst))
            del cls_inst.aliases[:]
        cls_inst.aliases.append(decl)


class source_reader_t:
    """
    This class reads C++ source code and returns the declarations tree.

    This class is the only class that works directly with GCC-XML or CastXML.

    It has only one responsibility: it calls GCC-XML with a source file
    specified by the user and creates declarations tree. The implementation of
    this class is split to two classes:

    1. `scanner_t` - this class scans the "XML" file, generated by GCC-XML
        or CastXML and creates :mod:`pygccxml` declarations and types classes.
        After the XML file has been processed declarations and type class
        instances keeps references to each other using GCC-XML or CastXML
        generated id's.

    2. `linker_t` - this class contains logic for replacing GCC-XML or CastXML
        generated ids with references to declarations or type class instances.
    """

    def __init__(self, config, cache=None, decl_factory=None, join_decls=True):
        """
        :param config: Instance of :class:`xml_generator_configuration_t`
                       class, that contains GCC-XML or CastXML configuration.

        :param cache: Reference to cache object, that will be updated after a
                      file has been parsed.
        :type cache: Instance of :class:`cache_base_t` class

        :param decl_factory: Declarations factory, if not given default
                             declarations factory( :class:`decl_factory_t` )
                             will be used.

        :param join_decls: Skip the joining of the declarations for the file.
                           This can then be done once, in the case where
                           there are multiple files, for example in the
                           project_reader. Is True per default.
        :type boolean

        """

        self.logger = utils.loggers.cxx_parser
        self.__join_decls = join_decls
        self.__search_directories = []
        self.__config = config
        self.__search_directories.append(config.working_directory)
        self.__search_directories.extend(config.include_paths)
        if not cache:
            cache = declarations_cache.dummy_cache_t()
        self.__dcache = cache
        self.__config.raise_on_wrong_settings()
        self.__decl_factory = decl_factory
        if not decl_factory:
            self.__decl_factory = declarations.decl_factory_t()

    def __create_command_line(self, source_file, xml_file):
        """
        Generate the command line used to build xml files.

        Depending on the chosen xml_generator a different command line
        is built. The gccxml option may be removed once gccxml
        support is dropped (this was the original c++ xml_generator,
        castxml is replacing it now).

        """

        if self.__config.xml_generator == "gccxml":
            return self.__create_command_line_gccxml(source_file, xml_file)
        elif self.__config.xml_generator == "castxml":
            return self.__create_command_line_castxml(source_file, xml_file)

    def __create_command_line_castxml(self, source_file, xmlfile):
        assert isinstance(self.__config, config.xml_generator_configuration_t)

        cmd = []

        # first is gccxml executable
        if platform.system() == 'Windows':
            cmd.append('"%s"' % os.path.normpath(
                self.__config.xml_generator_path))
        else:
            cmd.append('%s' % os.path.normpath(
                self.__config.xml_generator_path))

        # Add all cflags passed
        if self.__config.cflags != "":
            cmd.append(" %s " % self.__config.cflags)

        # Add additional includes directories
        dirs = self.__search_directories
        cmd.append(''.join([' -I%s' % search_dir for search_dir in dirs]))

        # Clang option: -c Only run preprocess, compile, and assemble steps
        cmd.append("-c")
        # Clang option: make sure clang knows we want to parse c++
        cmd.append("-x c++")

        # Platform specific options
        if platform.system() == 'Windows':

            if "mingw" in self.__config.compiler_path.lower():
                # Look at the compiler path. This is a bad way
                # to find out if we are using mingw; but it
                # should probably work in most of the cases
                cmd.append('--castxml-cc-gnu ' + self.__config.compiler_path)
            else:
                # We are using msvc
                cmd.append('--castxml-cc-msvc cl')
                if 'msvc9' == self.__config.compiler:
                    cmd.append('-D"_HAS_TR1=0"')
        else:

            # On mac or linux, use gcc or clang (the flag is the same)
            cmd.append('--castxml-cc-gnu ' + self.__config.compiler_path)

        # Tell castxml to output xml compatible files with gccxml
        # so that we can parse them with pygccxml
        cmd.append('--castxml-gccxml')

        # Add symbols
        cmd = self.__add_symbols(cmd)

        # The destination file
        cmd.append('-o %s' % xmlfile)
        # The source file
        cmd.append('%s' % source_file)
        # Where to start the parsing
        if self.__config.start_with_declarations:
            cmd.append(
                '--castxml-start "%s"' %
                ','.join(self.__config.start_with_declarations))
        cmd_line = ' '.join(cmd)
        self.logger.debug('castxml cmd: %s' % cmd_line)
        return cmd_line

    def __create_command_line_gccxml(self, source_file, xmlfile):
        assert isinstance(self.__config, config.xml_generator_configuration_t)
        # returns
        cmd = []
        # first is gccxml executable
        if 'nt' == os.name:
            cmd.append('"%s"' % os.path.normpath(
                self.__config.xml_generator_path))
        else:
            cmd.append('%s' % os.path.normpath(
                self.__config.xml_generator_path))

        # Add all cflags passed
        if self.__config.cflags != "":
            cmd.append(" %s " % self.__config.cflags)
        # second all additional includes directories
        dirs = self.__search_directories
        cmd.append(''.join([' -I"%s"' % search_dir for search_dir in dirs]))

        # Add symbols
        cmd = self.__add_symbols(cmd)

        # fourth source file
        cmd.append('"%s"' % source_file)
        # five destination file
        cmd.append('-fxml="%s"' % xmlfile)
        if self.__config.start_with_declarations:
            cmd.append(
                '-fxml-start="%s"' %
                ','.join(
                    self.__config.start_with_declarations))
        # Specify compiler if asked to
        if self.__config.compiler:
            cmd.append(" --gccxml-compiler %s" % self.__config.compiler)
        cmd_line = ' '.join(cmd)
        self.logger.debug('gccxml cmd: %s' % cmd_line)
        return cmd_line

    def __add_symbols(self, cmd):
        """
        Add all additional defined and undefined symbols.

        """

        if len(self.__config.define_symbols) != 0:
            symbols = self.__config.define_symbols
            cmd.append(''.join(
                [' -D"%s"' % defined_symbol for defined_symbol in symbols]))
        if len(self.__config.undefine_symbols) != 0:
            un_symbols = self.__config.undefine_symbols
            cmd.append(
                ''.join([' -U"%s"' % undefined_symbol for
                        undefined_symbol in un_symbols]))

        return cmd

    def create_xml_file(self, source_file, destination=None):
        """
        This method will generate a xml file using an external tool.

        The external tool can be either gccxml or castxml. The method will
        return the file path of the generated xml file.

        :param source_file: path to the source file that should be parsed.
        :type source_file: str

        :param destination: if given, will be used as target file path for
                            GCC-XML or CastXML.
        :type destination: str

        :rtype: path to xml file.

        """

        xml_file = destination
        # If file specified, remove it to start else create new file name
        if xml_file:
            pygccxml.utils.remove_file_no_raise(xml_file, self.__config)
        else:
            xml_file = pygccxml.utils.create_temp_file_name(suffix='.xml')
        try:
            ffname = source_file
            if not os.path.isabs(ffname):
                ffname = self.__file_full_name(source_file)
            command_line = self.__create_command_line(ffname, xml_file)

            process = subprocess.Popen(
                args=command_line,
                shell=True,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE)
            process.stdin.close()

            gccxml_reports = []
            while process.poll() is None:
                line = process.stdout.readline()
                if line.strip():
                    gccxml_reports.append(line.rstrip())
            for line in process.stdout.readlines():
                if line.strip():
                    gccxml_reports.append(line.rstrip())

            exit_status = process.returncode
            gccxml_msg = os.linesep.join([str(s) for s in gccxml_reports])
            if self.__config.ignore_gccxml_output:
                if not os.path.isfile(xml_file):
                    raise RuntimeError(
                        "Error occured while running " +
                        self.__config.xml_generator.upper() +
                        ": %s status:%s" %
                        (gccxml_msg, exit_status))
            else:
                if gccxml_msg or exit_status or not \
                        os.path.isfile(xml_file):
                    raise RuntimeError(
                        "Error occured while running " +
                        self.__config.xml_generator.upper() + ": %s" %
                        gccxml_msg)
        except Exception:
            pygccxml.utils.remove_file_no_raise(xml_file, self.__config)
            raise
        return xml_file

    def create_xml_file_from_string(self, content, destination=None):
        """
        Creates XML file from text.

        :param content: C++ source code
        :type content: str

        :param destination: file name for GCC-XML generated file
        :type destination: str

        :rtype: returns file name of GCC-XML generated file
        """
        header_file = pygccxml.utils.create_temp_file_name(suffix='.h')
        xml_file = None
        try:
            header_file_obj = open(header_file, 'w+')
            header_file_obj.write(content)
            header_file_obj.close()
            xml_file = self.create_xml_file(header_file, destination)
        finally:
            pygccxml.utils.remove_file_no_raise(header_file, self.__config)
        return xml_file

    def read_file(self, source_file):
        return self.read_cpp_source_file(source_file)

    def read_cpp_source_file(self, source_file):
        """
        Reads C++ source file and returns declarations tree

        :param source_file: path to C++ source file
        :type source_file: str

        """

        xml_file = ''
        try:
            ffname = self.__file_full_name(source_file)
            self.logger.debug("Reading source file: [%s]." % ffname)
            declarations = self.__dcache.cached_value(ffname, self.__config)
            if not declarations:
                self.logger.debug(
                    "File has not been found in cache, parsing...")
                xml_file = self.create_xml_file(ffname)
                declarations, files = self.__parse_xml_file(xml_file)
                self.__dcache.update(
                    ffname, self.__config, declarations, files)
            else:
                self.logger.debug(
                    ("File has not been changed, reading declarations " +
                        "from cache."))
        except Exception:
            if xml_file:
                pygccxml.utils.remove_file_no_raise(xml_file, self.__config)
            raise
        if xml_file:
            pygccxml.utils.remove_file_no_raise(xml_file, self.__config)

        return declarations

    def read_xml_file(self, xml_file):
        """
        Read generated XML file.

        :param xml_file: path to xml file
        :type xml_file: str

        :rtype: declarations tree

        """

        assert(self.__config is not None)

        ffname = self.__file_full_name(xml_file)
        self.logger.debug("Reading xml file: [%s]" % xml_file)
        declarations = self.__dcache.cached_value(ffname, self.__config)
        if not declarations:
            self.logger.debug("File has not been found in cache, parsing...")
            declarations, files = self.__parse_xml_file(ffname)
            self.__dcache.update(ffname, self.__config, declarations, [])
        else:
            self.logger.debug(
                "File has not been changed, reading declarations from cache.")

        return declarations

    def read_string(self, content):
        """
        Reads a Python string that contains C++ code, and return
        the declarations tree.

        """

        header_file = pygccxml.utils.create_temp_file_name(suffix='.h')
        with open(header_file, "w+") as f:
            f.write(content)

        try:
            declarations = self.read_file(header_file)
        except Exception:
            pygccxml.utils.remove_file_no_raise(header_file, self.__config)
            raise
        pygccxml.utils.remove_file_no_raise(header_file, self.__config)

        return declarations

    def __file_full_name(self, file):
        if os.path.isfile(file):
            return file
        for path in self.__search_directories:
            file_path = os.path.join(path, file)
            if os.path.isfile(file_path):
                return file_path
        raise RuntimeError("pygccxml error: file '%s' does not exist" % file)

    def __produce_full_file(self, file_path):
        if os.name in ['nt', 'posix']:
            file_path = file_path.replace(r'\/', os.path.sep)
        if os.path.isabs(file_path):
            return file_path
        try:
            abs_file_path = os.path.realpath(
                os.path.join(
                    self.__config.working_directory,
                    file_path))
            if os.path.exists(abs_file_path):
                return os.path.normpath(abs_file_path)
            return file_path
        except Exception:
            return file_path

    def __parse_xml_file(self, xml_file):
        scanner_ = scanner_t(xml_file, self.__decl_factory, self.__config)
        scanner_.read()
        decls = scanner_.declarations()
        types = scanner_.types()
        files = {}
        for file_id, file_path in scanner_.files().items():
            files[file_id] = self.__produce_full_file(file_path)
        linker_ = linker.linker_t(
            decls=decls,
            types=types,
            access=scanner_.access(),
            membership=scanner_.members(),
            files=files)
        for type_ in list(types.values()):
            # I need this copy because internaly linker change types collection
            linker_.instance = type_
            declarations.apply_visitor(linker_, type_)
        for decl in decls.values():
            linker_.instance = decl
            declarations.apply_visitor(linker_, decl)
        bind_aliases(iter(decls.values()))

        # Join declarations
        if self.__join_decls:
            for ns in iter(decls.values()):
                if isinstance(ns, pygccxml.declarations.namespace_t):
                    self.join_declarations(ns)

        # some times gccxml report typedefs defined in no namespace
        # it happens for example in next situation
        # template< typename X>
        # void ddd(){ typedef typename X::Y YY;}
        # if I will fail on this bug next time, the right way to fix it may be
        # different
        patcher.fix_calldef_decls(scanner_.calldefs(), scanner_.enums())
        decls = [
            inst for inst in iter(
                decls.values()) if isinstance(
                inst,
                declarations.namespace_t) and not inst.parent]
        return (decls, list(files.values()))

    def join_declarations(self, declref):
        self._join_namespaces(declref)
        for ns in declref.declarations:
            if isinstance(ns, pygccxml.declarations.namespace_t):
                self.join_declarations(ns)

    @staticmethod
    def _join_namespaces(nsref):
        assert isinstance(nsref, pygccxml.declarations.namespace_t)
        ddhash = {}
        decls = []

        for decl in nsref.declarations:
            if decl.__class__ not in ddhash:
                ddhash[decl.__class__] = {decl._name: [decl]}
                decls.append(decl)
            else:
                joined_decls = ddhash[decl.__class__]
                if decl._name not in joined_decls:
                    decls.append(decl)
                    joined_decls[decl._name] = [decl]
                else:
                    if isinstance(decl, pygccxml.declarations.calldef_t):
                        if decl not in joined_decls[decl._name]:
                            # functions has overloading
                            decls.append(decl)
                            joined_decls[decl._name].append(decl)
                    elif isinstance(decl, pygccxml.declarations.enumeration_t):
                        # unnamed enums
                        if not decl.name and decl not in \
                                joined_decls[decl._name]:
                            decls.append(decl)
                            joined_decls[decl._name].append(decl)
                    elif isinstance(decl, pygccxml.declarations.class_t):
                        # unnamed classes
                        if not decl.name and decl not in \
                                joined_decls[decl._name]:
                            decls.append(decl)
                            joined_decls[decl._name].append(decl)
                    else:
                        assert 1 == len(joined_decls[decl._name])
                        if isinstance(decl, pygccxml.declarations.namespace_t):
                            joined_decls[decl._name][0].take_parenting(decl)

        class_t = pygccxml.declarations.class_t
        class_declaration_t = pygccxml.declarations.class_declaration_t
        if class_t in ddhash and class_declaration_t in ddhash:
            # if there is a class and its forward declaration - get rid of the
            # second one.
            class_names = set()
            for name, same_name_classes in ddhash[class_t].items():
                if not name:
                    continue
                if "GCC" in utils.xml_generator:
                    class_names.add(same_name_classes[0].mangled)
                elif "CastXML" in utils.xml_generator:
                    class_names.add(same_name_classes[0].name)

            class_declarations = ddhash[class_declaration_t]
            for name, same_name_class_declarations in \
                    class_declarations.items():
                if not name:
                    continue
                for class_declaration in same_name_class_declarations:
                    if "GCC" in utils.xml_generator:
                        if class_declaration.mangled and \
                                class_declaration.mangled in class_names:
                                decls.remove(class_declaration)
                    elif "CastXML" in utils.xml_generator:
                        if class_declaration.name and \
                                class_declaration.name in class_names:
                                decls.remove(class_declaration)

        nsref.declarations = decls
