# Copyright 2004 Roman Yakovenko.
# Distributed under the Boost Software License, Version 1.0. (See
# accompanying file LICENSE_1_0.txt or copy at
# http://www.boost.org/LICENSE_1_0.txt)

"""
defines classes, that describes C++ classes

This modules contains definition for next C++ declarations:
    - class definition
    - class declaration
    - small helper class for describing C++ class hierarchy
"""

import scopedef
import algorithm
import declaration

class ACCESS_TYPES:
    """class that defines "access" constants"""
    PUBLIC = "public"
    PRIVATE = "private"
    PROTECTED = "protected"    
    ALL = [ PUBLIC, PRIVATE, PROTECTED ]

class CLASS_TYPES:
    """class that defines "class" type constants"""
    CLASS = "class"
    STRUCT = "struct"
    UNION = "union"
    ALL = [ CLASS, STRUCT, UNION ]

class hierarchy_info_t( object ):
    """
    describes class relationship
    """
    def __init__(self, related_class=None, access=None ):
        if related_class:
            assert( isinstance( related_class, class_t ) )
        self._related_class = related_class
        if access:
            assert( access in ACCESS_TYPES.ALL)
        self._access=access

    def __eq__(self, other):
        if not isinstance( other, hierarchy_info_t ):
            return False
        return algorithm.declaration_path( self.related_class ) == algorithm.declaration_path( other.related_class ) \
               and self.access == other.access

    def __ne__( self, other):
        return not self.__eq__( other )

    def __lt__(self, other):
        if not isinstance( other, self.__class__ ):
            return self.__class__.__name__ < other.__class__.__name__
        return ( algorithm.declaration_path( self.related_class ), self.access  ) \
               < ( algorithm.declaration_path( other.related_class ), other.access )

    def _get_related_class(self):
        return self._related_class
    def _set_related_class(self, new_related_class):
        if new_related_class:
            assert( isinstance( new_related_class, class_t ) )
        self._related_class = new_related_class
    related_class = property( _get_related_class, _set_related_class
                              , doc="reference to base or derived L{class<class_t>}")

    def _get_access(self):
        return self._access
    def _set_access(self, new_access):
        assert( new_access in ACCESS_TYPES.ALL )
        self._access = new_access
    access = property( _get_access, _set_access )
    access_type = property( _get_access, _set_access
                            , doc="describes L{hierarchy type<ACCESS_TYPES>}")

class class_declaration_t( declaration.declaration_t ):
    """describes class declaration"""
    def __init__( self, name='', parent='' ):
        declaration.declaration_t.__init__( self, name, parent )
    
    def _get__cmp__items(self):
        return []       

class class_t( scopedef.scopedef_t ):
    """describes class definition"""

    USE_DEMANGLED_AS_NAME = True
    def __init__( self, name='', parent=None, class_type=CLASS_TYPES.CLASS, is_abstract=False ):
        scopedef.scopedef_t.__init__( self, name, parent )
        if class_type:
            assert( class_type in CLASS_TYPES.ALL )
        self._class_type = class_type
        self._bases = []
        self._derived = []
        self._is_abstract = is_abstract
        self._public_members = []
        self._private_members = []
        self._protected_members = []
        self._aliases = []
        
    def _get_name_impl( self ):
        if not self._name: #class with empty name
            return self._name
        if class_t.USE_DEMANGLED_AS_NAME and self.demangled:
            fname = algorithm.full_name( self.parent )
            if fname.startswith( '::' ) and not self.demangled.startswith( '::' ):
                fname = fname[2:]
            if self.demangled.startswith( fname ):
                tmp = self.demangled[ len( fname ): ] #demangled::name
                if tmp.startswith( '::' ):
                    tmp = tmp[2:] 
                return tmp
            else:
                return self._name
        else:
            return self._name
        
    def __str__(self):
        name = algorithm.full_name(self)
        if name[:2]=="::":
            name = name[2:]
        return "%s [%s]"%(name, self.class_type)

    def _get__cmp__scope_items(self):
        return [ self.class_type     
                 , self._sorted_list( [ algorithm.declaration_path( base.related_class ) for base in self.bases ] )
                 , self._sorted_list( [ algorithm.declaration_path( derive.related_class ) for derive in self.derived ] )
                 , self.is_abstract                 
                 , self._sorted_list( self.public_members )
                 , self._sorted_list( self.private_members )
                 , self._sorted_list( self.protected_members ) ]
                 
    def __eq__(self, other):
        if not scopedef.scopedef_t.__eq__( self, other ):
            return False
        return self.class_type == other.class_type \
               and self._sorted_list( [ algorithm.declaration_path( base.related_class ) for base in self.bases ] ) \
                   == other._sorted_list( [ algorithm.declaration_path( base.related_class ) for base in other.bases ] ) \
               and self._sorted_list( [ algorithm.declaration_path( derive.related_class ) for derive in self.derived ] ) \
                   == other._sorted_list( [ algorithm.declaration_path( derive.related_class ) for derive in other.derived ] ) \
               and self.is_abstract == other.is_abstract \
               and self._sorted_list( self.public_members ) \
                   == other._sorted_list( other.public_members ) \
               and self._sorted_list( self.private_members ) \
                   == other._sorted_list( other.private_members ) \
               and self._sorted_list( self.protected_members ) \
                   == self._sorted_list( other.protected_members )

    def _get_class_type(self):
        return self._class_type
    def _set_class_type( self, new_class_type):
        if new_class_type:
            assert( new_class_type in CLASS_TYPES.ALL )
        self._class_type = new_class_type
    class_type = property( _get_class_type, _set_class_type
                           , doc="describes class L{type<CLASS_TYPES>}")

    def _get_bases(self):
        return self._bases
    def _set_bases( self, new_bases ):
        self._bases = new_bases
    bases = property( _get_bases, _set_bases
                      , doc="list of L{base classes<hierarchy_info_t>}")

    def _get_recursive_bases(self):
        to_go = self.bases[:]
        all_bases = []
        while to_go:
            base = to_go.pop()
            if base not in all_bases:
                all_bases.append( base )
                to_go.extend( base.related_class.bases )
        return all_bases
    recursive_bases = property( _get_recursive_bases
                                , doc="returns a list of all L{base classes<hierarchy_info_t>}")
    
    def _get_derived(self):
        return self._derived
    def _set_derived( self, new_derived ):
        self._derived = new_derived
    derived = property( _get_derived, _set_derived
                        , doc="list of L{derived classes<hierarchy_info_t>}")

    def _get_recursive_derived(self):
        to_go = self.derived[:]
        all_derived = []
        while to_go:
            derive = to_go.pop()
            if derive not in all_derived:
                all_derived.append( derive )
                to_go.extend( derive.related_class.derived )
        return all_derived
    recursive_derived = property( _get_recursive_derived
                                  , doc="returns a list of all L{derive classes<hierarchy_info_t>}")

    def _get_is_abstract(self):
        return self._is_abstract
    def _set_is_abstract( self, is_abstract ):
        self._is_abstract = is_abstract
    is_abstract = property( _get_is_abstract, _set_is_abstract
                            ,doc="describes whether class abstract or not" )

    def _get_public_members(self):
        return self._public_members
    def _set_public_members( self, new_public_members ):
        self._public_members = new_public_members
    public_members = property( _get_public_members, _set_public_members
                               , doc="list of all public L{members<declaration_t>}")

    def _get_private_members(self):
        return self._private_members
    def _set_private_members( self, new_private_members ):
        self._private_members = new_private_members
    private_members = property( _get_private_members, _set_private_members
                                , doc="list of all private L{members<declaration_t>}")

    def _get_protected_members(self):
        return self._protected_members
    def _set_protected_members( self, new_protected_members ):
        self._protected_members = new_protected_members
    protected_members = property( _get_protected_members, _set_protected_members
                                  , doc="list of all protected L{members<declaration_t>}" )

    def _get_aliases(self):
        return self._aliases
    def _set_aliases( self, new_aliases ):
        self._aliases = new_aliases
    aliases = property( _get_aliases, _set_aliases
                         , doc="List of L{aliases<typedef_t>} to this instance")

    def _get_declarations_impl(self):
        return self.get_members()

    def get_members( self, access=None):
        """
        returns list of members according to access type
        
        If access equals to None, then returned list will contain all members.
        
        @param access: describes desired members
        @type access: L{ACCESS_TYPES}
        
        @return: [ members ]
        """
        if access == ACCESS_TYPES.PUBLIC:
            return self.public_members
        elif access == ACCESS_TYPES.PROTECTED:
            return self.protected_members
        elif access == ACCESS_TYPES.PRIVATE:
            return self.private_members
        else:
            all_members = []
            all_members.extend( self.public_members )
            all_members.extend( self.protected_members )
            all_members.extend( self.private_members )
            return all_members

    def set_members( self, access, new_members ):
        """
        set list of members according to access type
        
        @param access: describes desired members
        @type access: L{ACCESS_TYPES}
        
        @param new_members: list of new members
        @type new_members: [ L{member<declaration_t>} ]
        """
        assert( access in ACCESS_TYPES.ALL )
        if access == ACCESS_TYPES.PUBLIC:
            self.public_members = new_members
        elif access == ACCESS_TYPES.PROTECTED:
            self.protected_members = new_members
        else:
            self.private_members = new_members
        for member in new_members:
            member.parent = self
   
    def remove_declaration( self, decl ):
        """
        removes decl from  members list
        
        @param decl: declaration to be removed
        @type decl: L{declaration_t}
        """
        container = None
        if decl in self.public_members:
            container = self.public_members
        elif decl in self.protected_members:
            container = self.protected_members
        elif decl in self.private_members:
            container = self.private_members
        else:
            raise ValueError()
        del container[ container.index( decl ) ]
        #add more comment about this.
        #if not keep_parent:
        #    decl.parent=None
        
    def find_out_member_access_type( self, member ):
        """
        returns member access type
        
        @param member: member of the class
        @type member: L{declaration_t}
        
        @return: L{ACCESS_TYPES}
        """
        assert member.parent is self
        if member in self.public_members:
            return ACCESS_TYPES.PUBLIC
        elif member in self.protected_members:
            return ACCESS_TYPES.PROTECTED
        elif member in self.private_members:
            return ACCESS_TYPES.PRIVATE
        else:
            raise RuntimeError( "Unable to find member within internal members list." )
