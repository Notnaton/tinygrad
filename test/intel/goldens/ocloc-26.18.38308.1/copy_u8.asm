L0:
(W)     mov (16|M0)              r127.0<1>:ud  0x0:ud                             
(W)     and (1|M0)               r127.2<1>:ud  r0.0<0;1,0>:ud    0xFFFFFFC0:ud             
(W)     and (1|M0)               r127.0<1>:uw  r0.4<0;1,0>:uw    0xFF:uw             
(W)     add (1|M0)               r127.2<1>:ud  r127.2<0;1,0>:ud  0x20:ud              {I@2}
(W)     add (1|M0)               r127.2<1>:ud  r127.2<0;1,0>:ud  0x0:ud              {I@1}
(W)     mad (1|M0)               r127.0<1>:ud  r127.2<0;0>:ud    r127.0<0;0>:uw    0x40:uw              {I@1}
(W)     mov (8|M0)               r2.0<1>:ud    r1.0<1;1,0>:ud                  
(W)     send.ugm (1|M0)          r1       r127  null:0  0xFF000000            0x6219D500           {A@1,$0} // wr:1+0, rd:1; load.ugm.d32x16t.a32.ca.cc.bti[255]
(W)     and (1|M0)               r127.0<1>:ud  r0.0<0;1,0>:ud    0xFFFFFFC0:ud              {$0.src}
(W)     add (1|M0)               r127.0<1>:ud  r127.0<0;1,0>:ud  0x0:ud              {I@1}
(W)     send.ugm (1|M0)          r3       r127  null:0  0xFF000000            0x6219C500           {I@1,$1} // wr:1+0, rd:1; load.ugm.d32x8t.a32.ca.cc.bti[255]
(W)     mov (16|M0)              r4.0<1>:ud    r0.0<1;1,0>:ud                   {Compacted}
(W)     or (1|M0)                cr0.0<1>:ud   cr0.0<0;1,0>:ud   0x400004C0:ud              {A@1}
(W)     mul (1|M0)               acc0.0<1>:ud  r2.3<0;1,0>:ud    r4.2<0;1,0>:uw   {A@1}
(W)     macl (1|M0)              r20.0<1>:ud   r2.3<0;1,0>:ud    r4.1<0;1,0>:ud   {Compacted}
(W)     mul (1|M0)               acc0.0<1>:ud  r2.3<0;1,0>:ud    r4.2<0;1,0>:uw  
(W)     mach (1|M0)              r5.0<1>:d     r2.3<0;1,0>:ud    r4.1<0;1,0>:ud  
        mov (16|M0)              r21.0<4>:uw   r1.0<1;1,0>:uw                   {$0.dst}
        mov (16|M16)             r23.0<4>:uw   r1.16<1;1,0>:uw                 
(W)     mov (1|M0)               r2.8<2>:ud    r20.0<0;1,0>:ud                  {I@5}
(W)     mov (1|M0)               r2.9<2>:d     r5.0<0;1,0>:d                    {I@4}
(W)     asr (1|M0)               r2.10<1>:d    r3.2<0;1,0>:d     31:w               {$1.dst}
        add (16|M0)              r25.0<1>:q    r2.4<0;1,0>:q     r21.0<4;1,0>:uw  {I@2}
        add (16|M16)             r27.0<1>:q    r2.4<0;1,0>:q     r23.0<4;1,0>:uw 
        add (16|M0)              r29.0<1>:q    r25.0<1;1,0>:q    r2.0<0;1,0>:ud   {I@2}
        add (16|M16)             r31.0<1>:q    r27.0<1;1,0>:q    r2.0<0;1,0>:ud   {I@2}
        mov (16|M0)              r6.0<1>:d     r29.0<2;1,0>:d                   {Compacted,I@2}
        mov (16|M16)             r7.0<1>:d     r31.0<2;1,0>:d                   {Compacted,I@2}
        cmp (32|M0)   (lt)f0.0   null<1>:ud    r6.0<1;1,0>:ud    r3.2<0;1,0>:ud   {I@1}
        mov (16|M0)              r8.0<1>:d     r29.1<2;1,0>:d                   {Compacted}
        mov (16|M16)             r9.0<1>:d     r31.1<2;1,0>:d                   {Compacted}
(f0.0)  cmp (32|M0)   (eq)f0.0   null<1>:d     r8.0<1;1,0>:d     r2.10<0;1,0>:d   {I@1}
(~f0.0) cmp (32|M0)   (lt)f0.0   null<1>:ud    r8.0<1;1,0>:ud    r2.10<0;1,0>:ud 
(~f0.0) goto (32|M0)                         L560                  L560                
L496:
        add (16|M0)              r10.0<1>:q    r29.0<1;1,0>:q    r2.3<0;1,0>:q    {Compacted}
        add (16|M16)             r12.0<1>:q    r31.0<1;1,0>:q    r2.3<0;1,0>:q    {Compacted}
        send.ugm (32|M0)         r14      r10  null:0  0x0            0x08200980           {I@1,$2} // wr:4+0, rd:2; load.ugm.d8u32.a64
        add (16|M0)              r16.0<1>:q    r29.0<1;1,0>:q    r3.0<0;1,0>:q    {Compacted}
        add (16|M16)             r18.0<1>:q    r31.0<1;1,0>:q    r3.0<0;1,0>:q    {Compacted}
        send.ugm (32|M0)         null     r16  r14:2  0x0            0x08000984           {I@1,$2} // wr:4+2, rd:0; store.ugm.d8u32.a64
L560:
        join (32|M0)                         L576                                
L576:
(W)     mov (16|M0)              r127.0<1>:f   r4.0<1;1,0>:f                    {Compacted}
(W)     send.gtwy (1|M0)         null     r127  null:0  0x0            0x02000010           {EOT,F@1,$3} // wr:1+0, rd:0; end of thread
L600:
(W)     mov (16|M0)              null<1>:ud    0x671DA9E5:ud                             
(W)     mov (16|M0)              null<1>:ud    0x423F1395:ud                             
(W)     mov (16|M0)              null<1>:ud    0x0:ud                             
(W)     mov (16|M0)              null<1>:ud    0x1:ud                             
        illegal                
        illegal                
        illegal                
        illegal                
        illegal                
        illegal                
        illegal                
        illegal                
        illegal                
        illegal
